from affinity_redesign.pipeline.rescore import apply_mutation, recommend_row
from affinity_redesign.schemas import RescoreConfig


def test_apply_mutation():
    seqs = {"H": "QITLE", "A": "AAAAA"}
    out = apply_mutation(seqs, "H", 3, "T", "S")
    assert out["H"] == "QISLE"
    assert seqs["H"] == "QITLE"


def test_recommend_keep_and_drop():
    cfg = RescoreConfig(delta_iptm_min=-0.03, max_ddg=3.0)
    keep = recommend_row(
        {"boltz2_status": "ok", "delta_iptm": 0.02, "ddG": 0.5, "tier": "A", "rosetta_flags": ""},
        cfg,
    )
    assert keep[0] == "keep" and keep[2] is True
    drop = recommend_row(
        {"boltz2_status": "ok", "delta_iptm": -0.08, "ddG": 0.1, "tier": "B", "rosetta_flags": ""},
        cfg,
    )
    assert drop[0] == "drop" and drop[2] is False
    review = recommend_row(
        {"boltz2_status": "ok", "delta_iptm": 0.0, "ddG": 5.0, "tier": "B", "rosetta_flags": ""},
        cfg,
    )
    assert review[0] == "review"
