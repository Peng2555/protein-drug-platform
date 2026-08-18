"""IgGM affinity maturation job creation and helpers."""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import is_fold_engine
from app.job_paths import job_output_dir
from app.job_service import fasta_from_seqs, sequence_hash
from app.md_service import resolve_structure_path
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from app.schemas import IgGMParams, MaturationJobCreate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boltz_runner import parse_fasta_text, pick_chain_key, sequences_from_structure, validate_boltz_chain_ids
from iggm_mask_builder import build_maturation_fastas, estimate_maturation_inference

from worker.tasks import run_maturation_job


def _tail_text(path: Path, max_lines: int = 250) -> tuple[str, bool]:
    if not path.is_file():
        return "", False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    truncated = len(lines) > max_lines
    if truncated:
        lines = lines[-max_lines:]
    return "\n".join(lines), truncated


def _parse_inference_total(log_text: str) -> int | None:
    import re

    m = re.search(r"#inference samples:\s*(\d+)", log_text)
    return int(m.group(1)) if m else None


def _parse_gpu_progress(log_text: str) -> tuple[int, int] | None:
    import re

    matches = re.findall(r"(\d+)/(\d+)\s+\[", log_text)
    if not matches:
        return None
    current, total = matches[-1]
    return int(current), int(total)


def collect_maturation_logs(job: Job, *, tail_lines: int = 250) -> dict:
    params = job.params_json or {}
    iggm = params.get("iggm") or params
    summary: list[str] = [
        f"任务 ID: {job.id}",
        f"状态: {job.status}" + (f" · 阶段: {job.stage}" if job.stage else ""),
    ]
    if job.started_at:
        summary.append(f"开始时间: {job.started_at.isoformat()}")
    if job.finished_at:
        summary.append(f"结束时间: {job.finished_at.isoformat()}")
    if job.runtime_seconds is not None:
        summary.append(f"耗时: {round(job.runtime_seconds)}s")
    if job.work_dir:
        summary.append(f"工作目录: {job.work_dir}")

    progress: dict = {}
    sections: list[dict] = []

    num_samples = int(iggm.get("num_samples", 100) or 100)
    gpu_count = int(iggm.get("gpu_count", 2) or 2)
    steps = int(iggm.get("steps", 10) or 10)
    progress["num_samples"] = num_samples
    progress["gpu_count"] = gpu_count
    progress["steps"] = steps
    mask_positions = int(params.get("mask_position_count") or 0)
    inference_total = int(params.get("estimated_inference_total") or 0)
    if mask_positions:
        progress["mask_position_count"] = mask_positions
    if inference_total:
        progress["inference_total"] = inference_total
        summary.append(
            f"预计总推理任务: {inference_total} "
            f"({num_samples}/位点 × {mask_positions or '?'} 掩码位)"
        )
    summary.append(f"多 GPU 并行抢占同一任务队列（非每卡各 {inference_total or '?'} 份输出）")

    work_dir = Path(job.work_dir) if job.work_dir else None
    if work_dir and work_dir.is_dir():
        mat_dir = work_dir / "maturation"
        if mat_dir.is_dir():
            fasta_files = [p for p in mat_dir.glob("*.fasta") if p.name != "mask.fasta"]
            progress["maturation_fastas"] = len(fasta_files)
            summary.append(f"已生成 FASTA 输出: {len(fasta_files)}")

            parsed_total = inference_total
            for log_path in sorted(mat_dir.glob("rank*.log")):
                content, truncated = _tail_text(log_path, tail_lines)
                if not parsed_total:
                    parsed_total = _parse_inference_total(content) or 0
                sections.append({
                    "id": log_path.stem,
                    "title": f"IgGM {log_path.name}",
                    "content": content or "(日志为空)",
                    "truncated": truncated,
                })
            if parsed_total and not inference_total:
                progress["inference_total"] = parsed_total
                inference_total = parsed_total
            if inference_total:
                progress["completion_percent"] = min(
                    100, round(100 * len(fasta_files) / inference_total)
                )
                summary.append(
                    f"完成度: {len(fasta_files)}/{inference_total} "
                    f"({progress['completion_percent']}%)"
                )

        for rel, title in (
            ("fold/error.log", "Boltz2 错误日志"),
            ("result.json", "流水线结果"),
        ):
            path = work_dir / rel
            if path.is_file():
                content, truncated = _tail_text(path, tail_lines)
                sections.append({
                    "id": rel.replace("/", "_").replace(".", "_"),
                    "title": title,
                    "content": content,
                    "truncated": truncated,
                })

        job_info = work_dir / "job_info.json"
        if job_info.is_file():
            content, truncated = _tail_text(job_info, 80)
            sections.append({
                "id": "job_info",
                "title": "job_info.json",
                "content": content,
                "truncated": truncated,
            })

    if job.error_message:
        sections.insert(0, {
            "id": "error",
            "title": "错误信息",
            "content": job.error_message,
            "truncated": len(job.error_message.splitlines()) > tail_lines,
        })

    if job.results_json:
        agg_err = job.results_json.get("aggregate_error")
        if agg_err:
            sections.append({
                "id": "aggregate_error",
                "title": "汇总阶段警告",
                "content": str(agg_err),
                "truncated": False,
            })

    src = params.get("structure_source")
    if src:
        summary.insert(1, f"结构来源: {src}")
    cdr = params.get("cdr_mask")
    if cdr:
        summary.insert(2, f"成熟 CDR: {', '.join(cdr) if isinstance(cdr, list) else cdr}")

    return {
        "stage": job.stage,
        "status": job.status,
        "summary_lines": summary,
        "progress": progress,
        "sections": sections,
    }


def validate_maturation_seqs(
    seqs: dict[str, str],
    binder_chain: str,
    antigen_chain: str,
    cdr_mask: list[str] | None = None,
) -> dict[str, str]:
    if len(seqs) < 2:
        raise HTTPException(400, "需要至少两条链（重链 + 抗原）")
    try:
        build_maturation_fastas(
            seqs,
            binder_chain_id=binder_chain,
            antigen_chain_id=antigen_chain,
            cdr_mask=cdr_mask or ["CDR-H3"],
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return seqs


def validate_maturation_fasta(
    fasta_text: str,
    binder_chain: str,
    antigen_chain: str,
    cdr_mask: list[str] | None = None,
) -> dict[str, str]:
    return validate_maturation_seqs(
        parse_fasta_text(fasta_text.strip()),
        binder_chain,
        antigen_chain,
        cdr_mask,
    )


def seqs_from_structure_file(
    structure_path: Path,
    binder_chain: str,
    antigen_chain: str,
    cdr_mask: list[str] | None = None,
) -> dict[str, str]:
    try:
        all_seqs = sequences_from_structure(structure_path)
        binder_key = pick_chain_key(all_seqs, binder_chain)
        antigen_key = pick_chain_key(all_seqs, antigen_chain)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return validate_maturation_seqs(
        {binder_key: all_seqs[binder_key], antigen_key: all_seqs[antigen_key]},
        binder_key,
        antigen_key,
        cdr_mask,
    )


def seqs_from_fold_parent(
    db: Session,
    user_id: str,
    fold_job_id: str,
    binder_chain: str,
    antigen_chain: str,
    cdr_mask: list[str] | None = None,
) -> dict[str, str]:
    parent = db.get(Job, fold_job_id)
    if not parent or parent.user_id != user_id:
        raise HTTPException(404, "Fold job not found")
    if not is_fold_engine(parent.engine):
        raise HTTPException(400, "Selected job is not a structure prediction job")
    if parent.status != JobStatus.done.value:
        raise HTTPException(409, f"Fold job status: {parent.status}")
    if not parent.fasta_text or not parent.fasta_text.strip():
        raise HTTPException(400, "所选折叠任务没有 FASTA 记录，请改从结构文件提取或手动填写序列")
    return validate_maturation_fasta(parent.fasta_text, binder_chain, antigen_chain, cdr_mask)


def resolve_maturation_sequences(
    db: Session,
    user_id: str,
    body: MaturationJobCreate,
    *,
    uploaded_structure: Path | None = None,
) -> dict[str, str]:
    if body.fasta and body.fasta.strip():
        return validate_maturation_fasta(
            body.fasta, body.binder_chain_id, body.antigen_chain_id, body.cdr_mask
        )

    if body.structure_source == "fold_job":
        if not body.fold_job_id:
            raise HTTPException(400, "fold_job_id required when structure_source=fold_job")
        structure_path = resolve_structure_for_maturation(db, user_id, body)
        try:
            return seqs_from_fold_parent(
                db,
                user_id,
                body.fold_job_id,
                body.binder_chain_id,
                body.antigen_chain_id,
                body.cdr_mask,
            )
        except HTTPException as exc:
            if exc.status_code != 400 or "没有 FASTA" not in str(exc.detail):
                raise
            if not structure_path or not structure_path.is_file():
                raise HTTPException(400, "请填写 FASTA，或确保折叠任务含结构文件") from exc
            return seqs_from_structure_file(
                structure_path,
                body.binder_chain_id,
                body.antigen_chain_id,
                body.cdr_mask,
            )

    if body.structure_source == "upload":
        if not uploaded_structure or not uploaded_structure.is_file():
            raise HTTPException(400, "请上传结构文件，或手动填写 FASTA")
        return seqs_from_structure_file(
            uploaded_structure,
            body.binder_chain_id,
            body.antigen_chain_id,
            body.cdr_mask,
        )

    raise HTTPException(400, "使用 Boltz2/ESMFold2 预测结构时必须提供 FASTA 序列")


def build_params_json(body: MaturationJobCreate) -> dict:
    iggm = (body.iggm or IgGMParams()).model_dump()
    params: dict = {
        "structure_source": body.structure_source,
        "fold_job_id": body.fold_job_id,
        "binder_chain_id": body.binder_chain_id,
        "antigen_chain_id": body.antigen_chain_id,
        "cdr_mask": body.cdr_mask,
        "iggm": iggm,
        **iggm,
    }
    if body.structure_source == "boltz2":
        params["fold_params"] = body.fold_params or {
            "use_msa_server": body.use_msa_server,
            "recycling_steps": 3,
            "sampling_steps": 200,
            "diffusion_samples": 1,
        }
    elif body.structure_source == "esmfold2":
        params["fold_params"] = body.fold_params or {
            "num_loops": 10,
            "num_sampling_steps": 68,
            "num_diffusion_samples": 5,
            "seed": 0,
        }
    return params


def resolve_structure_for_maturation(db: Session, user_id: str, body: MaturationJobCreate) -> Path | None:
    if body.structure_source == "upload":
        return None
    if body.structure_source == "fold_job":
        if not body.fold_job_id:
            raise HTTPException(400, "fold_job_id required when structure_source=fold_job")
        parent = db.get(Job, body.fold_job_id)
        if not parent or parent.user_id != user_id:
            raise HTTPException(404, "Fold job not found")
        if not is_fold_engine(parent.engine):
            raise HTTPException(400, "Selected job is not a structure prediction job")
        if parent.status != JobStatus.done.value:
            raise HTTPException(409, f"Fold job status: {parent.status}")
        return resolve_structure_path(parent)
    if body.structure_source in ("boltz2", "esmfold2"):
        return None
    raise HTTPException(400, f"Unknown structure_source: {body.structure_source}")


def create_and_queue_maturation_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    chains_json: dict[str, int],
    params_json: dict,
    structure_path: Path | None = None,
    fold_job_id: str | None = None,
) -> Job:
    from app.job_service import _check_user_queue_cap

    _check_user_queue_cap(db, user_id, "iggm_maturation")

    job = Job(
        user_id=user_id,
        parent_job_id=fold_job_id,
        name=name,
        engine="iggm_maturation",
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=fasta_text,
        sequence_hash=sequence_hash(parse_fasta_text(fasta_text)),
        chains_json=chains_json,
        total_length=sum(chains_json.values()),
        use_msa_server=False,
        params_json=params_json,
    )
    db.add(job)
    db.flush()

    work_dir = job_output_dir(settings.maturation_out_root, job.name, job.id, chains_json)
    work_dir.mkdir(parents=True, exist_ok=True)

    if structure_path and structure_path.is_file():
        struct_dir = work_dir / "input"
        struct_dir.mkdir(parents=True, exist_ok=True)
        dest = struct_dir / f"upload{structure_path.suffix.lower()}"
        if structure_path.resolve() != dest.resolve():
            shutil.copy2(structure_path, dest)
        job.params_json = {**(job.params_json or {}), "uploaded_structure": str(dest)}

    job.work_dir = str(work_dir)
    async_result = dispatch_to_gpu(run_maturation_job, job.id)
    job.celery_task_id = async_result.id
    return job


async def save_uploaded_structure(upload: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "input.pdb").suffix.lower()
    if suffix not in {".cif", ".mmcif", ".pdb", ".ent"}:
        raise HTTPException(400, "Upload .pdb or .cif structure file")
    dest = dest_dir / f"upload{suffix}"
    content = await upload.read()
    if len(content) < 100:
        raise HTTPException(400, "Structure file too small or empty")
    dest.write_bytes(content)
    return dest


def prepare_maturation_from_body(
    db: Session,
    user_id: str,
    body: MaturationJobCreate,
    *,
    uploaded_structure: Path | None = None,
) -> tuple[str, dict[str, int], dict, Path | None]:
    seqs = resolve_maturation_sequences(
        db, user_id, body, uploaded_structure=uploaded_structure
    )
    if body.structure_source in ("boltz2", "esmfold2"):
        normalized = {
            body.binder_chain_id: seqs[body.binder_chain_id],
            body.antigen_chain_id: seqs[body.antigen_chain_id],
        }
        try:
            validate_boltz_chain_ids({
                "H": normalized[body.binder_chain_id],
                "A": normalized[body.antigen_chain_id],
            })
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    structure_path = uploaded_structure
    if body.structure_source == "upload" and not structure_path:
        raise HTTPException(400, "Structure file required for upload mode")
    if body.structure_source == "fold_job":
        structure_path = resolve_structure_for_maturation(db, user_id, body)

    params = build_params_json(body)
    if not (body.fasta and body.fasta.strip()):
        params["sequences_from_structure"] = True

    iggm = (body.iggm or IgGMParams()).model_dump()
    try:
        mask_pos, inference_total = estimate_maturation_inference(
            seqs,
            binder_chain_id=body.binder_chain_id,
            antigen_chain_id=body.antigen_chain_id,
            cdr_mask=body.cdr_mask,
            num_samples=int(iggm.get("num_samples", 100)),
        )
        params["mask_position_count"] = mask_pos
        params["estimated_inference_total"] = inference_total
    except ValueError:
        pass

    chains_json = {k: len(v) for k, v in seqs.items()}
    fasta_text = fasta_from_seqs(seqs)
    return fasta_text, chains_json, params, structure_path
