"""Affinity redesign runtime progress and log collection."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from app.models import Job


def _tail_text(path: Path, max_lines: int = 250) -> tuple[str, bool]:
    if not path.is_file():
        return "", False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    truncated = len(lines) > max_lines
    if truncated:
        lines = lines[-max_lines:]
    return "\n".join(lines), truncated


def _count_merged_candidates(campaign_dir: Path) -> int:
    merged = campaign_dir / "round1" / "merged"
    total = 0
    for tier in ("A", "B", "C"):
        path = merged / f"tier_{tier}.csv"
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            total += sum(1 for _ in csv.DictReader(f))
    return total


def _count_boltz2_ok(campaign_dir: Path) -> tuple[int, int]:
    root = campaign_dir / "round1" / "rescore" / "boltz2"
    if not root.is_dir():
        return 0, 0
    ok = 0
    total = 0
    for result_path in root.glob("*/fold_result.json"):
        total += 1
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("status") == "ok":
            ok += 1
    return ok, max(total, ok)


def _load_mut_csv(path: Path, score_keys: tuple[str, ...] = ("mean_dll", "dll")) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            score = None
            for key in score_keys:
                raw = r.get(key)
                if raw not in (None, ""):
                    try:
                        score = float(raw)
                    except (TypeError, ValueError):
                        score = None
                    break
            rows.append(
                {
                    "chain": r.get("chain") or "H",
                    "position": int(r["position"]),
                    "wt": r.get("wt") or "",
                    "mut": r.get("mut") or "",
                    "region": r.get("region") or "",
                    "label": r.get("label") or "",
                    "score": score,
                }
            )
    rows.sort(key=lambda x: (x["chain"], x["position"], -(x["score"] if x["score"] is not None else 0)))
    return rows


def _count_rosetta_done(campaign_dir: Path) -> tuple[int, int]:
    root = campaign_dir / "round1" / "rescore" / "rosetta" / "variants"
    if not root.is_dir():
        return 0, 0
    dirs = [p for p in root.iterdir() if p.is_dir()]
    done = 0
    for var_dir in dirs:
        if (var_dir / "relax" / "best.pdb").is_file() or list((var_dir / "relax").glob("relax_*.pdb")):
            done += 1
    return done, len(dirs)


def _prefer_stage(job_stage: str | None, wf_stage: str | None) -> str | None:
    """DB 里的 boltz2_*/rosetta 比 workflow_status 的粗粒度 rescore 更准。"""
    fine = job_stage or ""
    if fine.startswith("boltz2") or fine in ("rosetta", "boltz2_wt", "done"):
        return job_stage
    return wf_stage or job_stage


def _parse_boltz2_stage(stage: str | None) -> dict:
    if not stage:
        return {}
    m = re.match(r"boltz2_(\d+)/(\d+)_(.+)", stage)
    if not m:
        return {}
    return {
        "boltz2_current": int(m.group(1)),
        "boltz2_total": int(m.group(2)),
        "boltz2_variant": m.group(3),
    }


def collect_affinity_redesign_progress(job: Job, *, tail_lines: int = 250) -> dict:
    params = job.params_json or {}
    stage = job.stage
    summary: list[str] = [
        f"任务 ID: {job.id}",
        f"状态: {job.status}" + (f" · 阶段: {stage}" if stage else ""),
    ]
    if params.get("entry_mode") == "structure":
        summary.append("入口: 已有复合物结构（跳过 WT 折叠）")
    else:
        summary.append("入口: 仅序列（先 Boltz2 折 WT 复合物）")
    if job.started_at:
        summary.append(f"开始时间: {job.started_at.isoformat()}")
    if job.finished_at:
        summary.append(f"结束时间: {job.finished_at.isoformat()}")
    if job.runtime_seconds is not None:
        summary.append(f"耗时: {round(job.runtime_seconds)}s")
    if job.work_dir:
        summary.append(f"Campaign: {job.work_dir}")

    progress: dict = dict(_parse_boltz2_stage(stage))
    workflow_status: dict | None = None
    sections: list[dict] = []
    plm_hits: list[dict] = []
    structure_hits: list[dict] = []

    campaign_dir = Path(job.work_dir) if job.work_dir else None
    if campaign_dir and campaign_dir.is_dir():
        wf_path = campaign_dir / "workflow_status.json"
        if wf_path.is_file():
            try:
                workflow_status = json.loads(wf_path.read_text(encoding="utf-8"))
                stage = _prefer_stage(stage, workflow_status.get("stage"))
                progress.update(_parse_boltz2_stage(str(stage) if stage else None))
            except json.JSONDecodeError:
                pass

        plm_hits = _load_mut_csv(campaign_dir / "round1" / "plm" / "top_per_chain.csv", ("mean_dll",))
        structure_hits = _load_mut_csv(
            campaign_dir / "round1" / "structure" / "top_per_chain.csv",
            ("dll",),
        )
        if plm_hits:
            progress["plm_n"] = len(plm_hits)
        if structure_hits:
            progress["structure_n"] = len(structure_hits)

        merged_n = _count_merged_candidates(campaign_dir)
        if merged_n:
            progress["merged_candidates"] = merged_n
            summary.append(f"Round1 合并候选: {merged_n}")

        boltz_ok, boltz_total = _count_boltz2_ok(campaign_dir)
        if boltz_ok or boltz_total:
            progress["boltz2_ok"] = boltz_ok
            progress["boltz2_done"] = boltz_total
            summary.append(f"Boltz2 已完成: {boltz_ok}/{boltz_total or merged_n or '?'}")
            if boltz_total and boltz_ok >= boltz_total:
                progress["boltz2_percent"] = 100
                progress["boltz2_current"] = progress.get("boltz2_current") or boltz_total
                progress["boltz2_total"] = progress.get("boltz2_total") or boltz_total

        ros_done, ros_total = _count_rosetta_done(campaign_dir)
        if ros_total:
            progress["rosetta_done"] = ros_done
            progress["rosetta_total"] = ros_total
            progress["rosetta_percent"] = min(100, round(100 * ros_done / ros_total)) if ros_total else 0
            summary.append(f"Rosetta: {ros_done}/{ros_total}")

        if progress.get("boltz2_total") and str(stage or "").startswith("boltz2"):
            cur = progress.get("boltz2_current", 0)
            tot = progress["boltz2_total"]
            progress["boltz2_percent"] = min(100, round(100 * cur / tot)) if tot else 0
            summary.append(f"当前 Boltz2 进度: {cur}/{tot} ({progress['boltz2_percent']}%)")
        elif merged_n and stage and str(stage).startswith("boltz2"):
            summary.append(f"当前阶段: {stage}")

        for rel, title in (
            ("round1/result.json", "Round1 结果"),
            ("exports/summary.json", "导出 summary"),
            ("exports/workflow_result.json", "流水线结果"),
        ):
            path = campaign_dir / rel
            if path.is_file():
                content, truncated = _tail_text(path, min(tail_lines, 120))
                sections.append({
                    "id": rel.replace("/", "_").replace(".", "_"),
                    "title": title,
                    "content": content,
                    "truncated": truncated,
                })

        log_paths: list[Path] = []
        for pattern in (
            "round1/rescore/boltz2/**/*.log",
            "round1/rescore/boltz2/**/fold.log",
            "round1/**/*.log",
            "logs/**/*.log",
        ):
            log_paths.extend(sorted(campaign_dir.glob(pattern)))
        seen: set[str] = set()
        for log_path in log_paths:
            key = str(log_path.relative_to(campaign_dir))
            if key in seen:
                continue
            seen.add(key)
            content, truncated = _tail_text(log_path, tail_lines)
            if not content.strip():
                continue
            sections.append({
                "id": key.replace("/", "_").replace(".", "_"),
                "title": key,
                "content": content,
                "truncated": truncated,
            })
            if len(sections) >= 12:
                break

    if job.error_message:
        sections.insert(0, {
            "id": "error",
            "title": "错误信息",
            "content": job.error_message,
            "truncated": len(job.error_message.splitlines()) > tail_lines,
        })

    return {
        "stage": stage,
        "status": job.status,
        "summary_lines": summary,
        "progress": progress,
        "sections": sections,
        "workflow_status": workflow_status,
        "plm_hits": plm_hits,
        "structure_hits": structure_hits,
    }
