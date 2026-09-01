from affinity_redesign.pipeline.rescore import apply_mutation, build_wt_mutant_fasta, recommend_row
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


def test_build_wt_mutant_fasta():
    seqs = {"H": "QITLE", "A": "AAAAA"}
    text = build_wt_mutant_fasta(
        seqs,
        [{"chain": "H", "position": 3, "wt": "T", "mut": "S", "label": "T3S", "variant_id": "H_T3S"}],
        antigen_chain="A",
    )
    assert ">WT chain=H role=wild-type" in text
    assert ">WT chain=A role=wild-type" in text
    assert "mutation=H:T3S" in text
    assert "QISLE" in text
    assert "role=antigen_unchanged" in text
    assert seqs["H"] == "QITLE"

