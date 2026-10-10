"""第二轮：有益单点组合。待实现。"""

from __future__ import annotations

import json
from pathlib import Path


def run_round2(campaign_dir: Path) -> dict:
    campaign_dir = campaign_dir.resolve()
    assays = campaign_dir / "wetlab" / "round1_assays.csv"
    if not assays.is_file():
        raise FileNotFoundError(
            f"请先填写湿实验结果: {assays}\n"
            "列建议: chain,position,wt,mut,fold_change,pass"
        )
    round2_dir = campaign_dir / "round2"
    round2_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "stub",
        "message": "round2 组合打分待实现",
        "assays_path": str(assays),
    }
    (round2_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result
