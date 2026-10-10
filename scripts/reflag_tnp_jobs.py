#!/usr/bin/env python3
"""按当前 thresholds.json 重打已完成 TNP 任务的绿/黄/红，写回磁盘和数据库。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from algorithm_paths import bootstrap_algorithm_paths

bootstrap_algorithm_paths()

from tnp_profile.constants import DISCLAIMER, THRESHOLDS_PATH
from tnp_profile.flags import flag_metrics, load_thresholds

OUT_ROOT = ROOT / "run" / "tnp_profile_outputs"


def _relabel(summary: dict, thresholds: dict) -> tuple[dict, list[dict], dict[str, str]]:
    raw = {k: summary.get(k) for k in ("L", "L3", "C", "PSH", "PPC", "PNC")}
    flagged = flag_metrics(raw, thresholds)
    metrics = []
    old_flags = {m.get("id"): m.get("flag") for m in (summary.get("metrics") or []) if m.get("id")}
    new_flags = {}
    for key, meta in flagged.items():
        metrics.append(
            {
                "id": key,
                "value": meta["value"],
                "flag": meta["flag"],
                "calibrated": meta["calibrated"],
                "thresholds": meta["thresholds"],
            }
        )
        new_flags[key] = meta["flag"]
    note = thresholds.get("note") or DISCLAIMER
    summary = dict(summary)
    summary["disclaimer"] = note
    summary["thresholds_note"] = note
    summary["metrics"] = metrics
    changed = {k: f"{old_flags.get(k)}->{new_flags[k]}" for k in new_flags if old_flags.get(k) != new_flags[k]}
    return summary, metrics, changed


def rewrite_job_dir(job_dir: Path, thresholds: dict) -> dict | None:
    metrics_path = job_dir / "score" / "metrics.json"
    if not metrics_path.is_file():
        return None
    summary = json.loads(metrics_path.read_text(encoding="utf-8"))
    summary, metrics, changed = _relabel(summary, thresholds)
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    metrics_path.write_text(text, encoding="utf-8")
    exports = job_dir / "exports" / "summary.json"
    if exports.parent.is_dir():
        exports.write_text(text, encoding="utf-8")
    wf = job_dir / "workflow_status.json"
    if wf.is_file():
        status = json.loads(wf.read_text(encoding="utf-8"))
        status["summary"] = summary
        wf.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"dir": job_dir.name, "changed": changed, "flags": {m["id"]: m["flag"] for m in metrics}}


def main() -> None:
    thresholds = load_thresholds(THRESHOLDS_PATH)
    disk_rows = []
    for job_dir in sorted(OUT_ROOT.iterdir()):
        if not job_dir.is_dir() or job_dir.name.startswith("_"):
            continue
        rec = rewrite_job_dir(job_dir, thresholds)
        if rec:
            disk_rows.append(rec)

    from app.core.database import SessionLocal
    from app.core.models import Job

    db = SessionLocal()
    db_n = 0
    try:
        jobs = db.query(Job).filter(Job.engine == "tnp_profile", Job.status == "done").all()
        for job in jobs:
            work = Path(job.work_dir) if job.work_dir else None
            summary = None
            if work and (work / "score" / "metrics.json").is_file():
                summary = json.loads((work / "score" / "metrics.json").read_text(encoding="utf-8"))
            elif job.results_json and (job.results_json.get("summary") or {}).get("PPC") is not None:
                summary, metrics, _changed = _relabel(dict(job.results_json["summary"]), thresholds)
            if not summary:
                continue
            compact = dict(job.results_json or {})
            compact["summary"] = summary
            compact["metrics"] = summary.get("metrics")
            compact["pred_cif"] = summary.get("pred_cif") or compact.get("pred_cif")
            job.results_json = compact
            db_n += 1
        db.commit()
    finally:
        db.close()

    n_changed = sum(1 for r in disk_rows if r["changed"])
    ppc_flags = {}
    for r in disk_rows:
        ppc_flags[r["flags"].get("PPC")] = ppc_flags.get(r["flags"].get("PPC"), 0) + 1
    print(f"disk jobs relabeled: {len(disk_rows)} (flag changed: {n_changed})")
    print(f"db jobs updated: {db_n}")
    print("PPC flags now:", ppc_flags)
    for r in disk_rows:
        if r["changed"]:
            print(r["dir"][:48], r["changed"])


if __name__ == "__main__":
    main()
