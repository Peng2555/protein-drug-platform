"""WT / 突变体能量比较的判定（不强制本机有 PyRosetta）。"""

from tm_disulfide.energy import energy_pass, summarize_pair_energy


def test_energy_pass_uses_score_without_ref_and_rejects_clash():
    wt = {
        "fa_score_noref": 100.0,
        "fa_rep": 50.0,
        "error": None,
        "disulfides_preserved": True,
        "designed_bonded": False,
    }
    mut = {
        "fa_score_noref": 90.0,
        "fa_rep": 52.0,
        "error": None,
        "disulfides_preserved": True,
        "designed_bonded": True,
    }
    ok, reasons, ddg = energy_pass(wt, mut)
    assert ok is True
    assert ddg == -10.0
    assert reasons == []

    mut["fa_score_noref"] = 105.0
    ok, reasons, ddg = energy_pass(wt, mut)
    assert ok is True
    assert ddg == 5.0

    mut["fa_score_noref"] = 90.0
    mut["fa_rep"] = 120.0
    ok, reasons, _ddg = energy_pass(wt, mut)
    assert ok is False
    assert "fa_rep_clash" in reasons

    mut["fa_rep"] = 52.0
    mut["designed_bonded"] = False
    ok, reasons, _ddg = energy_pass(wt, mut)
    assert ok is False
    assert "mut_not_bonded" in reasons


def test_summarize_pair_energy_requires_four_of_five_models():
    pair = {"pair_id": "A:6-A:110", "site1": {}, "site2": {}}
    models = [
        {"energy_pass": True, "ddg": -2.0},
        {"energy_pass": True, "ddg": -1.0},
        {"energy_pass": True, "ddg": -3.0},
        {"energy_pass": False, "ddg": 1.0},
        {"energy_pass": False, "ddg": 2.0},
    ]
    summary = summarize_pair_energy(pair, models)
    assert summary["n_models_passed"] == 3
    assert summary["pair_energy_pass"] is False
    assert summary["median_ddg"] == -1.0

    models[3]["energy_pass"] = True
    models[3]["ddg"] = -0.5
    summary = summarize_pair_energy(pair, models)
    assert summary["n_models_passed"] == 4
    assert summary["pair_energy_pass"] is True
