"""端到端工作流：可选折 WT → round1 → Boltz2 全量 + Rosetta → 导出。"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

import yaml

from affinity_redesign.common.fasta import parse_fasta_file
from affinity_redesign.common.structure import resolve_structure_path
from affinity_redesign.config import settings
from affinity_redesign.pipeline.prepare import prepare_campaign
from affinity_redesign.pipeline.rescore import run_rescore
from affinity_redesign.pipeline.round1 import _load_round1_config, run_round1
from affinity_redesign.schemas import AntibodyFormat, CampaignConfig
from affinity_redesign.tracks.boltz2 import fold_complex

_PKG_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = _PKG_ROOT / "campaigns" / "_template"


def create_campaign(slug: str, runs_root: Path | None = None) -> Path:
    root = runs_root or settings.affinity_runs_root
    dest = root / f"{slug}__{uuid.uuid4().hex[:8]}"
    if dest.exists():
        raise FileExistsError(f"目录已存在: {dest}")
    dest.mkdir(parents=True)
    for name in (
        "input",
        "prepare",
        "round1/plm",
        "round1/structure",
        "round1/merged",
        "round1/rescore",
        "wetlab",
        "round2",
        "exports",
    ):
        (dest / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(_TEMPLATE / "campaign.yaml", dest / "campaign.yaml")
    shutil.copy2(_TEMPLATE / "sequences.fasta", dest / "input" / "sequences.fasta")
    shutil.copy2(_TEMPLATE / "notes.md", dest / "notes.md")
    yaml_path = dest / "campaign.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    text = text.replace("name: example_antibody", f"name: {slug}")
    text = text.replace("slug: example_antibody", f"slug: {slug}")
    yaml_path.write_text(text, encoding="utf-8")
    return dest


def _write_status(campaign_dir: Path, payload: dict) -> None:
    path = campaign_dir / "workflow_status.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_complex_structure(
    campaign_dir: Path,
    campaign: CampaignConfig,
    *,
    on_stage: Callable[[str], None] | None = None,
) -> Path:
    """若无 complex.pdb：用 Boltz2 折 WT 并写入 input/complex.pdb。"""
    rel = campaign.structure.path or "input/complex.pdb"
    existing = resolve_structure_path(campaign_dir, rel)
    if existing is not None:
        return existing

    if on_stage:
        on_stage("fold_wt_complex")
    fasta = campaign_dir / "input" / "sequences.fasta"
    out_root = campaign_dir / "round1" / "rescore" / "boltz2"
    fold = fold_complex(fasta, out_root, "WT")
    if fold.get("status") != "ok" or not fold.get("pred_pdb"):
        raise RuntimeError(f"仅序列入口需要 WT 复合物，Boltz2 失败: {fold.get('error')}")
    dest = campaign_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fold["pred_pdb"], dest)

    yaml_path = campaign_dir / "campaign.yaml"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    data.setdefault("structure", {})
    data["structure"]["source"] = "boltz2"
    data["structure"]["path"] = rel
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dest


def bootstrap_campaign(
    *,
    slug: str,
    fasta: Path,
    complex_pdb: Path | None = None,
    runs_root: Path | None = None,
) -> Path:
    dest = create_campaign(slug, runs_root)
    shutil.copy2(fasta, dest / "input" / "sequences.fasta")
    seqs = parse_fasta_file(dest / "input" / "sequences.fasta")
    has_light = "L" in seqs
    fmt = AntibodyFormat.igg if has_light else AntibodyFormat.vhh
    yaml_path = dest / "campaign.yaml"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    data["antibody_format"] = fmt.value
    data.setdefault("chains", {})
    data["chains"]["heavy"] = "H" if "H" in seqs else next(iter(seqs))
    data["chains"]["light"] = "L" if has_light else None
    others = [k for k in seqs if k not in ("H", "L")]
    data["chains"]["antigen"] = "A" if "A" in seqs else (others[-1] if others else "A")
    if complex_pdb is not None:
        shutil.copy2(complex_pdb, dest / "input" / "complex.pdb")
        data.setdefault("structure", {})
        data["structure"]["source"] = "pdb"
        data["structure"]["path"] = "input/complex.pdb"
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dest


def run_workflow(
    campaign_dir: Path,
    *,
    skip_round1: bool = False,
    skip_rescore: bool = False,
    on_stage: Callable[[str], None] | None = None,
) -> dict:
    campaign_dir = campaign_dir.resolve()
    status: dict = {"status": "running", "campaign": str(campaign_dir), "stages": []}

    def stage(name: str) -> None:
        status["stage"] = name
        status["stages"].append(name)
        _write_status(campaign_dir, status)
        if on_stage:
            on_stage(name)

    campaign = CampaignConfig.from_yaml(campaign_dir / "campaign.yaml")
    stage("ensure_structure")
    ensure_complex_structure(campaign_dir, campaign, on_stage=on_stage)
    campaign = CampaignConfig.from_yaml(campaign_dir / "campaign.yaml")
    config = _load_round1_config(campaign_dir, campaign)

    round1_result = None
    if skip_round1:
        stage("skip_round1")
        result_path = campaign_dir / "round1" / "result.json"
        if result_path.is_file():
            round1_result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            prepare_campaign(campaign_dir)
            round1_result = run_round1(campaign_dir)
    else:
        stage("round1")
        round1_result = run_round1(campaign_dir)

    rescore_result = None
    if not skip_rescore:
        merged_dir = campaign_dir / "round1" / "merged"
        has_tiers = any((merged_dir / f"tier_{t}.csv").is_file() for t in ("A", "B", "C"))
        if not has_tiers:
            err_bits = []
            if isinstance(round1_result, dict):
                err_bits.extend(round1_result.get("errors") or [])
            detail = "; ".join(err_bits) if err_bits else "round1 未写出 tier_A/B/C.csv"
            raise RuntimeError(
                "无法进入 rescore：round1/merged 为空。"
                f" 常见原因是结构轨（AntiFold）失败导致双轨无法合并。详情: {detail}"
            )
        stage("rescore")
        rescore_result = run_rescore(
            campaign_dir,
            campaign,
            config,
            on_stage=on_stage,
        )

    status.update(
        {
            "status": "ok",
            "stage": "done",
            "round1": round1_result,
            "rescore": rescore_result,
            "exports": str(campaign_dir / "exports"),
        }
    )
    _write_status(campaign_dir, status)
    (campaign_dir / "exports" / "workflow_result.json").write_text(
        json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return status
