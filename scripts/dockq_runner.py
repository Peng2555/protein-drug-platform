#!/usr/bin/env python3
"""DockQ scoring: predicted complex vs reference (native) structure."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DOCKQ_PYTHON = Path(os.environ.get("DOCKQ_PYTHON", "/home/pengpai/data/envs/dockq/bin/python"))
GEMMI_PY = os.environ.get("GEMMI_PY", "/home/pengpai/data/envs/IgGM/bin/python")


def cif_to_pdb(cif_path: Path, pdb_path: Path) -> None:
    script = (
        "import gemmi\n"
        f"st = gemmi.read_structure({str(cif_path)!r})\n"
        "st.remove_ligands_and_waters()\n"
        f"st.write_pdb({str(pdb_path)!r})\n"
    )
    proc = subprocess.run([GEMMI_PY, "-c", script], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "CIF→PDB failed")


def dockq_score(model_pdb: Path, native_pdb: Path) -> dict:
    """Run DockQ and return best interface DockQ score."""
    if not model_pdb.is_file():
        return {"dockq": None, "error": f"model not found: {model_pdb}"}
    if not native_pdb.is_file():
        return {"dockq": None, "error": f"reference not found: {native_pdb}"}

    cmd = [str(DOCKQ_PYTHON), "-m", "DockQ", str(model_pdb), str(native_pdb), "--short"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 and "DockQ" not in text:
        return {"dockq": None, "error": text.strip()[:2000]}

    total_dockq = None
    best_line_dockq = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Total DockQ over"):
            try:
                total_dockq = float(line.split(":", 1)[1].split()[0])
            except (IndexError, ValueError):
                pass
        if line.startswith("DockQ ") and "mapping" in line:
            try:
                val = float(line.split()[1])
                best_line_dockq = val if best_line_dockq is None else max(best_line_dockq, val)
            except (IndexError, ValueError):
                pass

    dockq_val = total_dockq if total_dockq is not None else best_line_dockq
    return {
        "dockq": dockq_val,
        "dockq_total": total_dockq,
        "dockq_best_interface": best_line_dockq,
    }
