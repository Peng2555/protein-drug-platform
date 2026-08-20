#!/usr/bin/env python3
"""Venus-MAXWELL (ESM-IF) relative ΔΔG landscape for one PDB chain.

Run with the dedicated Maxwell env (needs fair-esm + torch_scatter):
  /home/pengpai/miniconda3/envs/maxwell/bin/python scripts/maxwell_landscape.py ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
import esm
import esm.inverse_folding
from biotite.structure import filter_backbone, get_chains
from biotite.structure.io import pdb

STANDARD_AA = list("ARNDCQEGHILKMFPSTWYV")


def load_pdb(fin: str, chain: str):
    pdbf = pdb.PDBFile.read(fin)
    structure = pdb.get_structure(pdbf, model=1)
    structure = structure[filter_backbone(structure)]
    all_chains = get_chains(structure)
    if chain not in all_chains:
        raise ValueError(f"链 {chain} 不在结构中（现有: {', '.join(all_chains) or '无'}）")
    return structure[[a.chain_id == chain for a in structure]]


def load_coords(fin: str, chain: str):
    structure = load_pdb(fin, chain)
    return esm.inverse_folding.util.extract_coords_from_structure(structure)


class MutantNetIF(nn.Module):
    def __init__(self, device: str = "cuda"):
        super().__init__()
        self.model, self.alphabet = esm.pretrained.esm_if1_gvp4_t16_142M_UR50()
        self.model.to(device)
        self.model.eval()
        vocab_size = len(self.alphabet)
        self.extra_head = nn.Sequential(
            nn.Linear(512, 512),
            nn.SELU(),
            nn.Linear(512, vocab_size),
        )
        self.aa_index = torch.tensor([self.alphabet.get_idx(a) for a in STANDARD_AA])
        self.device = device

    @torch.no_grad()
    def landscape(self, fin: str, chain: str):
        coords, native_seq = load_coords(fin, chain)
        batch = [(coords, None, native_seq)]
        converter = esm.inverse_folding.util.CoordBatchConverter(self.alphabet)
        coords_t, confidence, _strs, tokens, padding_mask = converter(batch, device=self.device)
        prev = tokens[:, :-1].to(self.device)
        logits, _ = self.model.forward(coords_t, padding_mask, confidence, prev)
        logits = logits.transpose(1, 2)
        logits = torch.log_softmax(logits, dim=-1)
        one_hot = F.one_hot(tokens[:, 1:], num_classes=len(self.alphabet))
        logits = logits - (logits * one_hot).sum(dim=-1, keepdim=True)
        logits = logits.squeeze()
        table = torch.zeros((len(logits), len(STANDARD_AA)))
        for i in range(len(logits)):
            table[i, :] = logits[i, self.aa_index]
        # Venus-MAXWELL: lower relative_ddg = more stabilizing
        return native_seq, (-table).cpu().tolist()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdb_file", required=True)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--ckpt_path", required=True)
    parser.add_argument("--output_file", required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    device = args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        device = "cpu"

    model = MutantNetIF(device=device)
    state = torch.load(args.ckpt_path, map_location="cpu", weights_only=False)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    model.load_state_dict(state, strict=False)
    model.eval()
    seq, landscape = model.landscape(args.pdb_file, args.chain)
    rows = []
    for i, wt in enumerate(seq):
        for j, mut in enumerate(STANDARD_AA):
            rows.append({
                "pos": i + 1,
                "wt": wt,
                "mut": mut,
                "ddg": round(float(landscape[i][j]), 4),
                "is_wt": mut == wt,
            })
    payload = {
        "chain": args.chain,
        "sequence": seq,
        "length": len(seq),
        "engine": "venus-maxwell-esmif",
        "note": "relative_ddg：越低越稳定（相对野生型景观）",
        "rows": rows,
    }
    Path(args.output_file).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": True, "chain": args.chain, "length": len(seq), "output": args.output_file}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
