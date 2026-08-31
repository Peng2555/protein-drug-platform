"""第一轮：双轨打分 + 合并。"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from affinity_redesign.pipeline.merge import (
    load_plm_top_csv,
    load_structure_top_csv,
    merge_tracks,
)
from affinity_redesign.pipeline.prepare import prepare_campaign
from affinity_redesign.schemas import CampaignConfig, Round1Config
from affinity_redesign.tracks.antifold import score_structure_track
from affinity_redesign.tracks.plm import score_plm_track


def _load_round1_config(campaign_dir: Path, campaign: CampaignConfig) -> Round1Config:
    if campaign.round1_config:
        path = (campaign_dir / campaign.round1_config).resolve()
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            cfg = Round1Config.model_validate(data)
            return cfg.model_copy(
                update={
                    "antibody_format": campaign.antibody_format,
                    "chains": campaign.chains,
                    "structure": campaign.structure,
                }
            )
    default = Path(__file__).resolve().parents[3] / "configs" / "round1_default.yaml"
    if default.is_file():
        data = yaml.safe_load(default.read_text(encoding="utf-8"))
        cfg = Round1Config.model_validate(data)
    else:
        cfg = Round1Config()
    return cfg.model_copy(
        update={
            "antibody_format": campaign.antibody_format,
            "chains": campaign.chains,
            "structure": campaign.structure,
        }
    )


def run_round1(
    campaign_dir: Path,
    *,
    plm_only: bool = False,
    structure_only: bool = False,
) -> dict:
    campaign_dir = campaign_dir.resolve()
    manifest = prepare_campaign(campaign_dir)
    campaign = CampaignConfig.from_yaml(campaign_dir / "campaign.yaml")
    config = _load_round1_config(campaign_dir, campaign)

    round1_dir = campaign_dir / "round1"
    plm_out = round1_dir / "plm"
    struct_out = round1_dir / "structure"
    merged_out = round1_dir / "merged"
    round1_dir.mkdir(parents=True, exist_ok=True)

    do_plm = not structure_only
    do_struct = not plm_only

    plm_result: dict | None = None
    struct_result: dict | None = None
    errors: list[str] = []

    if do_plm:
        try:
            plm_result = score_plm_track(campaign_dir, config, plm_out)
        except Exception as exc:
            errors.append(f"plm: {exc}")

    if do_struct:
        try:
            struct_result = score_structure_track(campaign_dir, config, struct_out)
        except Exception as exc:
            errors.append(f"structure: {exc}")

    tiers = {"A": [], "B": [], "C": []}
    if (
        do_plm
        and do_struct
        and plm_result
        and struct_result
        and plm_result.get("status") == "ok"
        and struct_result.get("status") == "ok"
    ):
        plm_csv = Path(plm_result["top_csv"])
        struct_csv = Path(struct_result["top_csv"])
        tiers = merge_tracks(
            load_plm_top_csv(plm_csv),
            load_structure_top_csv(struct_csv),
            config.merge,
            merged_out,
        )

    status = "ok" if not errors else ("partial" if plm_result or struct_result else "failed")
    if plm_only and plm_result and not errors:
        status = "ok"
    if structure_only and struct_result and not errors:
        status = "ok"

    result = {
        "status": status,
        "plm": plm_result,
        "structure": struct_result,
        "errors": errors,
        "manifest_candidates": manifest.get("candidates"),
        "tiers": {k: len(v) for k, v in tiers.items()},
        "tier_labels": {k: [r.label for r in v] for k, v in tiers.items()},
        "merged_dir": str(merged_out) if any(tiers.values()) else None,
        "mode": "plm_only" if plm_only else ("structure_only" if structure_only else "both"),
    }
    (round1_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if status == "failed":
        raise RuntimeError("; ".join(errors) or "round1 failed")
    return result
