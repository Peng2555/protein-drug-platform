"""Campaign 输入校验、强制双轨结构、写出 candidates。"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from affinity_redesign.common.candidates import (
    build_candidates_for_campaign,
    write_candidates_csv,
)
from affinity_redesign.common.fasta import parse_fasta_file
from affinity_redesign.common.structure import resolve_structure_path
from affinity_redesign.schemas import CampaignConfig, FilterConfig, Round1Config


def _binder_chains(cfg: CampaignConfig) -> list[str]:
    chains = [cfg.chains.heavy]
    if cfg.chains.light:
        chains.append(cfg.chains.light)
    return chains


def _load_round1_defaults(campaign_dir: Path, campaign: CampaignConfig) -> Round1Config:
    if campaign.round1_config:
        path = (campaign_dir / campaign.round1_config).resolve()
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return Round1Config.model_validate(data)
    # 仓库默认配置
    default = (
        Path(__file__).resolve().parents[3] / "configs" / "round1_default.yaml"
    )
    if default.is_file():
        data = yaml.safe_load(default.read_text(encoding="utf-8"))
        cfg = Round1Config.model_validate(data)
    else:
        cfg = Round1Config()
    # 用 campaign 覆盖格式与链
    return cfg.model_copy(
        update={
            "antibody_format": campaign.antibody_format,
            "chains": campaign.chains,
            "structure": campaign.structure,
        }
    )


def prepare_campaign(campaign_dir: Path) -> dict:
    campaign_dir = campaign_dir.resolve()
    campaign_yaml = campaign_dir / "campaign.yaml"
    if not campaign_yaml.is_file():
        raise FileNotFoundError(f"缺少 campaign.yaml: {campaign_yaml}")

    cfg = CampaignConfig.from_yaml(campaign_yaml)
    fasta_path = campaign_dir / "input" / "sequences.fasta"
    if not fasta_path.is_file():
        raise FileNotFoundError(f"缺少 sequences.fasta: {fasta_path}")

    seqs = parse_fasta_file(fasta_path)
    binders = _binder_chains(cfg)
    antigen = cfg.chains.antigen

    for cid in binders:
        if cid not in seqs:
            raise ValueError(f"FASTA 中未找到 binder 链 {cid!r}")
    if antigen not in seqs:
        raise ValueError(f"FASTA 中未找到抗原链 {antigen!r}")

    # 双轨强制：必须有复合物结构
    struct_path = resolve_structure_path(campaign_dir, cfg.structure.path)
    if struct_path is None:
        raise FileNotFoundError(
            "双轨流程要求复合物结构。"
            f"请提供 {cfg.structure.path or 'input/complex.pdb'} "
            "（抗体可变区 + 抗原）。"
        )

    round1 = _load_round1_defaults(campaign_dir, cfg)
    scan_regions = round1.plm.scan_regions  # FR+CDR
    filters = round1.filters

    raw, filtered, annotations = build_candidates_for_campaign(
        seqs,
        binders,
        scan_regions=scan_regions,
        filters=filters,
    )

    prepare_dir = campaign_dir / "prepare"
    prepare_dir.mkdir(parents=True, exist_ok=True)

    domains = {cid: annotations[cid]["domain"] for cid in annotations}
    raw_path = prepare_dir / "candidates.csv"
    filtered_path = prepare_dir / "candidates_filtered.csv"
    write_candidates_csv(raw, raw_path, domains=domains)
    write_candidates_csv(filtered, filtered_path, domains=domains)

    manifest = {
        "name": cfg.name,
        "slug": cfg.slug,
        "antibody_format": cfg.antibody_format.value,
        "chains": cfg.chains.model_dump(),
        "binder_chains": binders,
        "sequence_lengths": {k: len(v) for k, v in seqs.items()},
        "structure": {
            "source": cfg.structure.source,
            "path": str(struct_path),
            "required": True,
            "multichain": cfg.structure.multichain,
        },
        "annotations": annotations,
        "candidates": {
            "raw_count": len(raw),
            "filtered_count": len(filtered),
            "raw_csv": str(raw_path.relative_to(campaign_dir)),
            "filtered_csv": str(filtered_path.relative_to(campaign_dir)),
            "scan_regions": scan_regions,
            "filters": filters.model_dump(),
        },
        "dual_track": {
            "plm_input": "prepare/candidates_filtered.csv",
            "structure_input": "prepare/candidates_filtered.csv",
            "structure_pdb": str(Path(struct_path).relative_to(campaign_dir)),
        },
    }
    manifest_path = prepare_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest
