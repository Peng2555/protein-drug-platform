#!/usr/bin/env python3
"""标定 VHH 可开发性画像阈值。默认只切 L/L3（Kabat，36 条临床序列）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tnp_profile" / "src"))
sys.path.insert(0, str(ROOT / "affinity_redesign" / "src"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasta", type=Path, default=None)
    args = parser.parse_args()
    from tnp_profile.calibrate import calibrate_sequence_metrics, write_thresholds

    payload = calibrate_sequence_metrics(args.fasta)
    dest = write_thresholds(payload)
    print(f"wrote {dest}")
    for key, spec in (payload.get("metrics") or {}).items():
        print(key, spec)


if __name__ == "__main__":
    main()
