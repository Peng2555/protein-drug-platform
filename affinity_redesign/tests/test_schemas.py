from pathlib import Path

import yaml

from affinity_redesign.schemas import CampaignConfig, Round1Config


def test_campaign_template_loads():
    root = Path(__file__).resolve().parents[1]
    path = root / "campaigns" / "_template" / "campaign.yaml"
    cfg = CampaignConfig.from_yaml(path)
    assert cfg.slug == "example_antibody"
    assert cfg.chains.heavy == "H"


def test_round1_default_loads():
    root = Path(__file__).resolve().parents[1]
    path = root / "configs" / "round1_default.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg = Round1Config.model_validate(data)
    assert cfg.plm.top_per_chain == 0
    assert cfg.structure_track.top_per_chain == 0
    assert cfg.structure_track.engine == "antifold"
    assert cfg.rescore.nstruct == 1
    assert cfg.merge.tier_quotas["B"] == 100
