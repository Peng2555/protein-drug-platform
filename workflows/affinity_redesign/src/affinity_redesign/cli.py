"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from affinity_redesign.pipeline.prepare import prepare_campaign
from affinity_redesign.pipeline.round1 import run_round1
from affinity_redesign.pipeline.round2 import run_round2
from affinity_redesign.pipeline.workflow import bootstrap_campaign, create_campaign, run_workflow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="affinity-redesign", description="抗体亲和力双轨改造")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="从模板创建新 campaign")
    p_new.add_argument("slug", help="抗体/campaign 短名，如 my_nanobody_v1")
    p_new.add_argument("--runs-root", type=Path, default=None)

    p_init = sub.add_parser("init", help="校验 campaign 输入并写 candidates")
    p_init.add_argument("--campaign", type=Path, required=True)

    p_plm = sub.add_parser("plm", help="只跑序列 PLM 轨（ESM-1b/1v）")
    p_plm.add_argument("--campaign", type=Path, required=True)

    p_struct = sub.add_parser("structure", help="只跑结构轨（AntiFold / ESM-IF1）")
    p_struct.add_argument("--campaign", type=Path, required=True)

    p_r1 = sub.add_parser("round1", help="运行第一轮（双轨；可用 --plm-only / --structure-only）")
    p_r1.add_argument("--campaign", type=Path, required=True)
    p_r1.add_argument("--plm-only", action="store_true", help="只跑 PLM 轨")
    p_r1.add_argument("--structure-only", action="store_true", help="只跑结构轨")

    p_wf = sub.add_parser(
        "workflow",
        help="端到端：结构（可选折 WT）→ round1 → Boltz2 全量 + Rosetta → exports",
    )
    p_wf.add_argument("--campaign", type=Path, default=None, help="已有 campaign 目录")
    p_wf.add_argument("--from-fasta", type=Path, default=None, help="从 FASTA 新建 campaign")
    p_wf.add_argument("--complex", type=Path, default=None, help="可选：已有复合物 PDB/CIF")
    p_wf.add_argument("--slug", default="antibody", help="配合 --from-fasta 的短名")
    p_wf.add_argument("--runs-root", type=Path, default=None)
    p_wf.add_argument("--skip-round1", action="store_true", help="复用已有 round1/merged")
    p_wf.add_argument("--skip-rescore", action="store_true", help="只跑到 round1，不跑 Boltz2/Rosetta")

    p_r2 = sub.add_parser("round2", help="运行第二轮组合（需 wetlab/round1_assays.csv）")
    p_r2.add_argument("--campaign", type=Path, required=True)

    args = parser.parse_args(argv)

    try:
        if args.command == "new":
            dest = create_campaign(args.slug, args.runs_root)
            print(json.dumps({"ok": True, "campaign_dir": str(dest)}, ensure_ascii=False))
            return 0
        if args.command == "init":
            manifest = prepare_campaign(args.campaign.resolve())
            print(json.dumps({"ok": True, "manifest": manifest}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "plm":
            result = run_round1(args.campaign.resolve(), plm_only=True)
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "structure":
            result = run_round1(args.campaign.resolve(), structure_only=True)
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "round1":
            if args.plm_only and args.structure_only:
                raise ValueError("--plm-only 与 --structure-only 不能同时使用")
            result = run_round1(
                args.campaign.resolve(),
                plm_only=args.plm_only,
                structure_only=args.structure_only,
            )
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "workflow":
            if args.campaign:
                dest = args.campaign.resolve()
            elif args.from_fasta:
                dest = bootstrap_campaign(
                    slug=args.slug,
                    fasta=args.from_fasta.resolve(),
                    complex_pdb=args.complex.resolve() if args.complex else None,
                    runs_root=args.runs_root,
                )
            else:
                raise ValueError("请提供 --campaign 或 --from-fasta")
            result = run_workflow(
                dest,
                skip_round1=args.skip_round1,
                skip_rescore=args.skip_rescore,
            )
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "round2":
            result = run_round2(args.campaign)
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
