"""ProteinMPNN sequence design runner.

调用本机 ProteinMPNN 脚本（默认 RFantibody 内置版本），将结构约束下的设计序列写入 work_dir。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class DesignResult:
    status: str
    stage: str
    seconds: float
    results: dict
    error: str | None = None


def _cif_to_pdb(gemmi_py: str, cif_path: Path, pdb_path: Path) -> None:
    code = (
        "import sys\n"
        "from gemmi import read_structure\n"
        "st = read_structure(sys.argv[1])\n"
        "st.write_minimal_pdb(sys.argv[2])\n"
    )
    proc = subprocess.run(
        [gemmi_py, "-c", code, str(cif_path), str(pdb_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0 or not pdb_path.is_file():
        raise RuntimeError(f"CIF→PDB 转换失败: {proc.stderr or proc.stdout or 'unknown'}")


def _ensure_pdb(structure_path: Path, work_dir: Path, gemmi_py: str) -> Path:
    suffix = structure_path.suffix.lower()
    if suffix == ".pdb":
        return structure_path
    if suffix in {".cif", ".mmcif"}:
        pdb_path = work_dir / "structure.pdb"
        _cif_to_pdb(gemmi_py, structure_path, pdb_path)
        return pdb_path
    raise RuntimeError(f"不支持的结构格式: {suffix}")


def _parse_designed_chains(raw: str) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    return [c for c in re.split(r"[\s,;]+", str(raw).strip()) if c]


def _parse_mpnn_fasta(path: Path) -> list[dict]:
    """Parse ProteinMPNN fasta output into candidate records."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    candidates: list[dict] = []
    header = None
    seq_parts: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if header is not None:
                candidates.append(_candidate_from_record(header, "".join(seq_parts)))
            header = line[1:].strip()
            seq_parts = []
        else:
            seq_parts.append(line.strip())
    if header is not None:
        candidates.append(_candidate_from_record(header, "".join(seq_parts)))
    # first entry is often the native/original sequence
    for i, c in enumerate(candidates):
        c["index"] = i
        c["is_native"] = i == 0 and ("sample=" not in (c.get("header") or "").lower())
    return candidates


def _candidate_from_record(header: str, seq: str) -> dict:
    score = None
    global_score = None
    seq_recovery = None
    temp = None
    sample = None
    m = re.search(r"score=([0-9.]+)", header)
    if m:
        score = float(m.group(1))
    m = re.search(r"global_score=([0-9.]+)", header)
    if m:
        global_score = float(m.group(1))
    m = re.search(r"seq_recovery=([0-9.]+)", header)
    if m:
        seq_recovery = float(m.group(1))
    m = re.search(r"T=([0-9.]+)", header)
    if m:
        temp = float(m.group(1))
    m = re.search(r"sample=(\d+)", header)
    if m:
        sample = int(m.group(1))
    # ProteinMPNN uses / to separate chains
    chains = [s for s in seq.split("/") if s]
    return {
        "header": header,
        "sequence": seq.replace("/", ""),
        "chain_sequences": chains,
        "score": score,
        "global_score": global_score,
        "seq_recovery": seq_recovery,
        "temperature": temp,
        "sample": sample,
    }


def run_design_job(
    *,
    work_dir: Path,
    params: dict,
    on_stage: Callable[[str], None] | None = None,
) -> DesignResult:
    t0 = time.time()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    def stage(name: str) -> None:
        if on_stage:
            on_stage(name)

    try:
        stage("prepare")
        structure_path = Path(params.get("structure_path") or "")
        if not structure_path.is_file():
            raise RuntimeError("缺少结构文件 structure_path")

        gemmi_py = str(params.get("gemmi_py") or "python3")
        pdb_path = _ensure_pdb(structure_path, work_dir, gemmi_py)

        mpnn_py = str(params.get("proteinmpnn_python") or "")
        mpnn_script = Path(params.get("proteinmpnn_script") or "")
        weights_dir = Path(params.get("proteinmpnn_weights_dir") or "")
        model_name = str(params.get("proteinmpnn_model_name") or "v_48_020")

        if not mpnn_py or not Path(mpnn_py).exists():
            raise RuntimeError(
                "未配置 ProteinMPNN Python。请在 .env 设置 PROTEINMPNN_PYTHON。"
            )
        if not mpnn_script.is_file():
            raise RuntimeError(
                f"未找到 ProteinMPNN 脚本: {mpnn_script}。请设置 PROTEINMPNN_SCRIPT。"
            )
        weight_file = weights_dir / f"{model_name}.pt"
        if not weight_file.is_file():
            raise RuntimeError(
                f"未找到权重文件: {weight_file}。请设置 PROTEINMPNN_WEIGHTS_DIR / PROTEINMPNN_MODEL_NAME。"
            )

        designed = _parse_designed_chains(str(params.get("designed_chains") or ""))
        num_seq = int(params.get("num_seq_per_target") or 8)
        sampling_temp = float(params.get("sampling_temp") or 0.1)
        seed = int(params.get("seed") or 0)
        backbone_noise = float(params.get("backbone_noise") or 0.0)
        omit_aas = str(params.get("omit_aas") or "X")

        mpnn_out = work_dir / "mpnn_out"
        if mpnn_out.exists():
            shutil.rmtree(mpnn_out)
        mpnn_out.mkdir(parents=True, exist_ok=True)

        cmd = [
            mpnn_py,
            str(mpnn_script),
            "--suppress_print",
            "1",
            "--path_to_model_weights",
            str(weights_dir),
            "--model_name",
            model_name,
            "--out_folder",
            str(mpnn_out),
            "--pdb_path",
            str(pdb_path),
            "--num_seq_per_target",
            str(num_seq),
            "--sampling_temp",
            str(sampling_temp),
            "--batch_size",
            "1",
            "--seed",
            str(seed),
            "--backbone_noise",
            str(backbone_noise),
            "--omit_AAs",
            omit_aas,
        ]
        if designed:
            cmd.extend(["--pdb_path_chains", " ".join(designed)])

        stage("mpnn")
        proc = subprocess.run(
            cmd,
            cwd=str(mpnn_script.parent),
            capture_output=True,
            text=True,
            timeout=3600,
        )
        (work_dir / "mpnn_stdout.log").write_text(proc.stdout or "", encoding="utf-8")
        (work_dir / "mpnn_stderr.log").write_text(proc.stderr or "", encoding="utf-8")
        if proc.returncode != 0:
            raise RuntimeError(
                f"ProteinMPNN 运行失败 (code={proc.returncode}): "
                f"{(proc.stderr or proc.stdout or '')[-2000:]}"
            )

        stage("parse")
        # ProteinMPNN writes seqs/*.fa
        fasta_files = sorted((mpnn_out / "seqs").glob("*.fa")) if (mpnn_out / "seqs").is_dir() else []
        if not fasta_files:
            fasta_files = sorted(mpnn_out.rglob("*.fa"))
        if not fasta_files:
            raise RuntimeError("ProteinMPNN 未产出序列 FASTA")

        # Prefer the main designed fasta (usually one per pdb)
        main_fa = fasta_files[0]
        shutil.copy2(main_fa, work_dir / "designed_sequences.fa")
        candidates = _parse_mpnn_fasta(main_fa)
        designed_only = [c for c in candidates if not c.get("is_native")]
        if not designed_only and len(candidates) > 1:
            designed_only = candidates[1:]
        if not designed_only:
            designed_only = candidates

        summary = {
            "engine": "protein_mpnn",
            "structure": structure_path.name,
            "pdb": pdb_path.name,
            "designed_chains": designed or "all",
            "num_seq_per_target": num_seq,
            "sampling_temp": sampling_temp,
            "n_candidates": len(designed_only),
            "model_name": model_name,
            "output_files": [
                "designed_sequences.fa",
                "candidates.json",
                "summary.json",
                "mpnn_stdout.log",
                "mpnn_stderr.log",
            ],
        }
        (work_dir / "candidates.json").write_text(
            json.dumps(designed_only, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (work_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Write a simple CSV
        csv_lines = ["index,sample,score,global_score,seq_recovery,sequence"]
        for c in designed_only:
            csv_lines.append(
                ",".join(
                    [
                        str(c.get("index", "")),
                        str(c.get("sample") or ""),
                        "" if c.get("score") is None else f"{c['score']:.4f}",
                        "" if c.get("global_score") is None else f"{c['global_score']:.4f}",
                        "" if c.get("seq_recovery") is None else f"{c['seq_recovery']:.4f}",
                        c.get("sequence") or "",
                    ]
                )
            )
        (work_dir / "candidates.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
        summary["output_files"].append("candidates.csv")

        stage("done")
        return DesignResult(
            status="ok",
            stage="done",
            seconds=round(time.time() - t0, 3),
            results={
                **summary,
                "top_score": designed_only[0].get("score") if designed_only else None,
                "top_seq_recovery": designed_only[0].get("seq_recovery") if designed_only else None,
                "candidates_preview": designed_only[:5],
            },
        )
    except Exception as exc:
        stage("failed")
        return DesignResult(
            status="error",
            stage="failed",
            seconds=round(time.time() - t0, 3),
            results={},
            error=str(exc)[:8000],
        )
