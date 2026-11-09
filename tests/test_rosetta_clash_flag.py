"""severe_clash 相对野生型 fa_rep 判断，不拿复合物的绝对排斥能一刀切。"""

import importlib.util
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "rosetta_eval_runner.py"
    spec = importlib.util.spec_from_file_location("rosetta_eval_runner", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_large_complex_baseline_is_not_a_mutation_clash():
    mod = _load()
    wt = {"fa_rep": 599.0, "is_wt": True}
    assert "severe_clash" not in mod._qc_flags(wt, None)
    near = {"fa_rep": 630.0, "is_wt": False}
    assert "severe_clash" not in mod._qc_flags(near, wt)
    worse = {"fa_rep": 650.0, "is_wt": False}
    assert "severe_clash" in mod._qc_flags(worse, wt)


def test_absolute_cutoff_only_when_there_is_no_wild_type():
    mod = _load()
    assert "severe_clash" in mod._qc_flags({"fa_rep": 250.0, "is_wt": False}, None)
    assert "severe_clash" not in mod._qc_flags({"fa_rep": 150.0, "is_wt": False}, None)
