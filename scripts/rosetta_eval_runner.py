#!/usr/bin/env python3
"""Rosetta antibody–antigen structural evaluation SOP.

Boltz2/ESMFold 复合物 → PDB 标准化 → 约束 FastRelax → InterfaceAnalyzer
→ WT 相对 ΔΔG / ΔE → 多指标排序。

本机未安装 Rosetta 时，会给出明确的 ROSETTA_BIN 配置错误，而不是静默跳过。
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class EvalResult:
    status: str
    stage: str
    seconds: float
    results: dict
    error: str | None = None


def _which_app(bin_dir: Path | None, prefixes: tuple[str, ...]) -> Path | None:
    search: list[Path] = []
    if bin_dir and bin_dir.is_dir():
        search.append(bin_dir)
    env_bin = os.environ.get("ROSETTA_BIN") or os.environ.get("ROSETTA3")
    if env_bin:
        p = Path(env_bin)
        search.append(p if p.name == "bin" or not (p / "bin").is_dir() else p / "bin")
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        if raw:
            search.append(Path(raw))
    seen: set[Path] = set()
    for folder in search:
        folder = folder.expanduser()
        if folder in seen or not folder.is_dir():
            continue
        seen.add(folder)
        names = sorted(folder.iterdir()) if folder.is_dir() else []
        for prefix in prefixes:
            for path in names:
                if path.is_file() and os.access(path, os.X_OK) and path.name.startswith(prefix):
                    return path
    return None


def resolve_rosetta_apps(bin_dir: str | Path | None = None) -> dict[str, Path]:
    folder = Path(bin_dir) if bin_dir else None
    relax = _which_app(folder, ("relax.default.", "relax.linux", "relax.static", "relax."))
    analyzer = _which_app(
        folder,
        ("InterfaceAnalyzer.default.", "InterfaceAnalyzer.linux", "InterfaceAnalyzer.static", "InterfaceAnalyzer."),
    )
    missing = [name for name, app in (("relax", relax), ("InterfaceAnalyzer", analyzer)) if app is None]
    if missing:
        raise RuntimeError(
            "未找到 Rosetta 可执行文件: "
            + ", ".join(missing)
            + "。请安装 Rosetta 3.14+，并在 .env 设置 ROSETTA_BIN_DIR"
        )
    return {"relax": relax, "interface_analyzer": analyzer}  # type: ignore[return-value]


def _pyrosetta_importable(python: str | None = None) -> bool:
    exe = python or sys.executable
    if Path(exe).resolve() == Path(sys.executable).resolve():
        try:
            import pyrosetta  # noqa: F401

            return True
        except Exception:
            return False
    try:
        proc = subprocess.run(
            [exe, "-c", "import pyrosetta"],
            capture_output=True,
            text=True,
            timeout=90,
        )
        return proc.returncode == 0
    except Exception:
        return False


def resolve_eval_backend(
    bin_dir: str | Path | None = None,
    pyrosetta_python: str | None = None,
) -> dict[str, Any]:
    """Prefer in-process PyRosetta, then dedicated interpreter, then CLI binaries."""
    if _pyrosetta_importable():
        return {"backend": "pyrosetta", "python": sys.executable}
    py = pyrosetta_python or os.environ.get("PYROSETTA_PYTHON") or ""
    if py and Path(py).is_file() and _pyrosetta_importable(py):
        return {"backend": "pyrosetta", "python": py, "reexec": True}
    try:
        apps = resolve_rosetta_apps(bin_dir)
        return {"backend": "cli", **apps}
    except RuntimeError as exc:
        raise RuntimeError(
            "未找到 PyRosetta 或 Rosetta 命令行。"
            "请运行 bash scripts/install_pyrosetta.sh，"
            "并在 .env 设置 PYROSETTA_PYTHON=/home/pengpai/data/envs/pyrosetta/bin/python"
        ) from exc


_PYROSETTA_INIT = False


def _ensure_pyrosetta(weights: str = "ref2015"):
    global _PYROSETTA_INIT
    import pyrosetta

    if not _PYROSETTA_INIT:
        pyrosetta.init(
            " ".join(
                [
                    "-mute all",
                    "-ignore_unrecognized_res",
                    "-ignore_zero_occupancy false",
                    "-use_input_sc",
                    "-ex1",
                    "-ex2",
                    "-flip_HNQ",
                    "-no_optH false",
                    "-relax:constrain_relax_to_start_coords true",
                    "-relax:coord_constrain_sidechains true",
                    "-relax:ramp_constraints false",
                    f"-score:weights {weights}",
                ]
            )
        )
        _PYROSETTA_INIT = True
    return pyrosetta


def _score_term(pose, name: str, sfxn=None) -> float | None:
    try:
        if sfxn is not None:
            sfxn(pose)
        from pyrosetta.rosetta.core.scoring import ScoreType

        st = getattr(ScoreType, name, None)
        if st is None:
            return None
        return float(pose.energies().total_energies()[st])
    except Exception:
        return None


def _make_fastrelax(sfxn):
    from pyrosetta.rosetta.protocols.relax import FastRelax

    fr = FastRelax()
    fr.set_scorefxn(sfxn)
    for method, value in (
        ("constrain_relax_to_start_coords", True),
        ("coord_constrain_sidechains", True),
        ("ramp_down_constraints", False),
    ):
        fn = getattr(fr, method, None)
        if callable(fn):
            try:
                fn(value)
            except Exception:
                pass
    return fr


def _relax_one_model(
    pdb: Path,
    dest: Path,
    *,
    weights: str = "ref2015",
) -> float:
    """Run a single constrained FastRelax and write dest PDB. Returns total_score."""
    pyrosetta = _ensure_pyrosetta(weights)
    from pyrosetta import create_score_function, pose_from_pdb

    del pyrosetta  # silence unused if version not needed
    sfxn = create_score_function(weights)
    fr = _make_fastrelax(sfxn)
    pose = pose_from_pdb(str(pdb))
    fr.apply(pose)
    score = float(sfxn(pose))
    dest.parent.mkdir(parents=True, exist_ok=True)
    pose.dump_pdb(str(dest))
    return score


def _pool_worker_init(weights: str) -> None:
    global _PYROSETTA_INIT
    _PYROSETTA_INIT = False
    _ensure_pyrosetta(weights)


def _pool_relax_task(payload: dict[str, Any]) -> dict[str, Any]:
    score = _relax_one_model(
        Path(payload["pdb"]),
        Path(payload["dest"]),
        weights=payload["weights"],
    )
    return {
        "name": payload["name"],
        "index": payload["index"],
        "score": score,
        "dest": payload["dest"],
    }


def _pool_interface_task(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = analyze_interface_pyrosetta(
        Path(payload["pdb"]),
        Path(payload["out_dir"]),
        interface=payload["interface"],
        weights=payload["weights"],
    )
    return {"name": payload["name"], "metrics": metrics}


def _auto_n_jobs() -> int:
    """尽量吃满 CPU，只留少量核给系统 / GPU worker / API。"""
    cpu = os.cpu_count() or 8
    reserve = min(8, max(2, cpu // 16))
    return max(1, cpu - reserve)


def default_n_jobs(requested: int | None = None, *, work_dir: Path | None = None) -> int:
    """并行进程数：0/未指定 = 自动（核数减预留）；显式正数按请求（不超过 cpu）。"""
    cpu = os.cpu_count() or 8
    auto = _auto_n_jobs()
    if requested in (None, ""):
        env = os.environ.get("ROSETTA_N_JOBS")
        if env not in (None, "", "0", "auto"):
            try:
                return max(1, min(int(env), cpu))
            except ValueError:
                pass
        return auto
    try:
        n = int(requested)
    except (TypeError, ValueError):
        return auto
    if n <= 0:
        return auto
    # 亲和力改造旧默认 8：大机器上视为未指定，避免 128 核只用 8 路
    if n == 8 and auto > 32 and work_dir is not None and "affinity_redesign" in str(work_dir):
        return auto
    return max(1, min(n, cpu))


def relax_structure_pyrosetta(
    pdb: Path,
    out_dir: Path,
    *,
    nstruct: int,
    weights: str = "ref2015",
) -> dict[str, Any]:
    pyrosetta = _ensure_pyrosetta(weights)
    out_dir.mkdir(parents=True, exist_ok=True)
    models: list[tuple[float, Path]] = []
    log_lines = [f"PyRosetta FastRelax nstruct={nstruct} weights={weights}"]
    for i in range(max(1, nstruct)):
        dest = out_dir / f"relax_{i + 1:04d}.pdb"
        score = _relax_one_model(pdb, dest, weights=weights)
        models.append((score, dest))
        log_lines.append(f"model {i + 1} total_score={score:.3f} file={dest.name}")
    models.sort(key=lambda x: x[0])
    best_score, best_pdb = models[0]
    shutil.copy2(best_pdb, out_dir / "best.pdb")
    scorefile = out_dir / "relax.sc"
    scorefile.write_text(
        "SCORE: total_score description\n"
        + "\n".join(f"SCORE: {s:.3f} {p.stem}" for s, p in models)
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "relax.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return {
        "best_pdb": str(out_dir / "best.pdb"),
        "nstruct": nstruct,
        "n_models": len(models),
        "total_score": best_score,
        "scorefile": str(scorefile),
        "models": [p.name for _, p in models],
        "backend": "pyrosetta",
        "pyrosetta_version": getattr(pyrosetta, "__version__", "quarterly"),
    }


def _finalize_variant_relax(
    name: str,
    out_dir: Path,
    model_rows: list[tuple[int, float, Path]],
    *,
    nstruct: int,
    weights: str,
    n_jobs: int,
) -> dict[str, Any]:
    model_rows = sorted(model_rows, key=lambda x: x[1])
    best_score, best_pdb = model_rows[0][1], model_rows[0][2]
    shutil.copy2(best_pdb, out_dir / "best.pdb")
    by_index = sorted(model_rows, key=lambda x: x[0])
    scorefile = out_dir / "relax.sc"
    scorefile.write_text(
        "SCORE: total_score description\n"
        + "\n".join(f"SCORE: {s:.3f} {p.stem}" for _, s, p in by_index)
        + "\n",
        encoding="utf-8",
    )
    log_lines = [
        f"PyRosetta FastRelax nstruct={nstruct} weights={weights} n_jobs={n_jobs} variant={name}",
        *[f"model {idx} total_score={s:.3f} file={p.name}" for idx, s, p in by_index],
        f"best={best_pdb.name} total_score={best_score:.3f}",
    ]
    (out_dir / "relax.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return {
        "best_pdb": str(out_dir / "best.pdb"),
        "nstruct": nstruct,
        "n_models": len(model_rows),
        "total_score": best_score,
        "scorefile": str(scorefile),
        "models": [p.name for _, _, p in by_index],
        "backend": "pyrosetta",
        "n_jobs": n_jobs,
    }


def parallel_relax_pyrosetta(
    prepared: list[dict[str, Any]],
    *,
    nstruct: int,
    weights: str,
    n_jobs: int,
) -> None:
    """Fill item['relax'] / item['total_score'] for each prepared variant in parallel."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import multiprocessing as mp

    tasks: list[dict[str, Any]] = []
    for item in prepared:
        out_dir = Path(item["var_dir"]) / "relax"
        out_dir.mkdir(parents=True, exist_ok=True)
        for i in range(max(1, nstruct)):
            tasks.append(
                {
                    "name": item["name"],
                    "index": i + 1,
                    "pdb": item["clean_pdb"],
                    "dest": str(out_dir / f"relax_{i + 1:04d}.pdb"),
                    "weights": weights,
                }
            )
    workers = max(1, min(n_jobs, len(tasks)))
    collected: dict[str, list[tuple[int, float, Path]]] = {item["name"]: [] for item in prepared}
    if workers == 1 or len(tasks) == 1:
        for task in tasks:
            row = _pool_relax_task(task)
            collected[row["name"]].append((row["index"], row["score"], Path(row["dest"])))
    else:
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=ctx,
            initializer=_pool_worker_init,
            initargs=(weights,),
        ) as pool:
            futures = [pool.submit(_pool_relax_task, t) for t in tasks]
            for fut in as_completed(futures):
                row = fut.result()
                collected[row["name"]].append((row["index"], row["score"], Path(row["dest"])))
    for item in prepared:
        out_dir = Path(item["var_dir"]) / "relax"
        relax = _finalize_variant_relax(
            item["name"],
            out_dir,
            collected[item["name"]],
            nstruct=nstruct,
            weights=weights,
            n_jobs=workers,
        )
        item["relax"] = relax
        item["total_score"] = relax.get("total_score")


def parallel_interface_pyrosetta(
    prepared: list[dict[str, Any]],
    *,
    interface: str,
    weights: str,
    n_jobs: int,
) -> None:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import multiprocessing as mp

    tasks = []
    for item in prepared:
        out_dir = Path(item["var_dir"]) / "interface"
        tasks.append(
            {
                "name": item["name"],
                "pdb": item["relax"]["best_pdb"],
                "out_dir": str(out_dir),
                "interface": interface,
                "weights": weights,
            }
        )
    workers = max(1, min(n_jobs, len(tasks)))
    results: dict[str, dict[str, Any]] = {}
    if workers == 1 or len(tasks) == 1:
        for task in tasks:
            row = _pool_interface_task(task)
            results[row["name"]] = row["metrics"]
    else:
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=ctx,
            initializer=_pool_worker_init,
            initargs=(weights,),
        ) as pool:
            futures = [pool.submit(_pool_interface_task, t) for t in tasks]
            for fut in as_completed(futures):
                row = fut.result()
                results[row["name"]] = row["metrics"]
    for item in prepared:
        item["interface"] = results[item["name"]]


def analyze_interface_pyrosetta(
    pdb: Path,
    out_dir: Path,
    *,
    interface: str,
    weights: str = "ref2015",
) -> dict[str, Any]:
    _ensure_pyrosetta(weights)
    from pyrosetta import create_score_function, pose_from_pdb
    from pyrosetta.rosetta.core.pose import DockingPartners
    from pyrosetta.rosetta.protocols.analysis import InterfaceAnalyzerMover

    out_dir.mkdir(parents=True, exist_ok=True)
    pose = pose_from_pdb(str(pdb))
    sfxn = create_score_function(weights)
    iam = InterfaceAnalyzerMover()
    iam.set_interface(DockingPartners.docking_partners_from_string(interface))
    iam.set_pack_separated(True)
    if hasattr(iam, "set_compute_packstat"):
        iam.set_compute_packstat(True)
    if hasattr(iam, "set_compute_interface_sc"):
        iam.set_compute_interface_sc(True)
    if hasattr(iam, "set_scorefunction"):
        iam.set_scorefunction(sfxn)
    iam.apply(pose)
    data = iam.get_all_data() if hasattr(iam, "get_all_data") else None

    def _d(*names: str):
        if data is None:
            return None
        for name in names:
            if hasattr(data, name):
                try:
                    val = getattr(data, name)
                    if callable(val):
                        val = val()
                    if isinstance(val, (int, float)):
                        return float(val)
                except Exception:
                    continue
        return None

    def _g(*names: str):
        for name in names:
            fn = getattr(iam, name, None)
            if not callable(fn):
                continue
            try:
                val = fn()
                if isinstance(val, (int, float)):
                    return float(val)
            except Exception:
                continue
        return None

    metrics = {
        "dG_separated": _d("dG", "separated_interface_score") or _g("get_separated_interface_energy", "get_interface_dG"),
        "dG_separated_dSASA": _d("dG_dSASA_ratio"),
        "dSASA_int": _d("dSASA") or _g("get_interface_delta_sasa"),
        "dSASA_hphobic": _d("dhSASA"),
        "dSASA_polar": None,
        "hbonds_int": _d("interface_hbonds"),
        "sc_value": _d("sc_value"),
        "packstat": _d("packstat") or _g("get_interface_packstat"),
        "nres_int": _d("interface_nres") or _g("get_num_interface_residues"),
        "fa_rep": _score_term(pose, "fa_rep", sfxn),
        "delta_unsat_hbonds": _d("delta_unsat_hbonds"),
        "complex_normalized": None,
        "raw": {
            "dG": _d("dG"),
            "dSASA": _d("dSASA"),
            "interface_hbonds": _d("interface_hbonds"),
            "sc_value": _d("sc_value"),
            "packstat": _d("packstat"),
        },
        "backend": "pyrosetta",
    }
    (out_dir / "interface.log").write_text(
        json.dumps({k: v for k, v in metrics.items() if k != "raw"}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return metrics


def _sanitize_label(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^\w\-]+", "_", (text or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "variant")[:max_len]


def _load_structure(path: Path):
    import gemmi

    suffix = path.suffix.lower()
    if suffix in {".cif", ".mmcif"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        sanitized = re.sub(r"^data_[^\s#]+", "data_pred", text, count=1, flags=re.M)
        tmp = path.with_name(path.stem + "__ascii.cif")
        if sanitized != text:
            tmp.write_text(sanitized, encoding="utf-8")
            path = tmp
        try:
            st = gemmi.read_structure(str(path))
        except Exception:
            doc = gemmi.cif.read(str(path))
            st = gemmi.make_structure_from_block(doc[0]) if hasattr(gemmi, "make_structure_from_block") else gemmi.read_structure(str(path))
    else:
        st = gemmi.read_structure(str(path))
    if len(st) == 0:
        raise ValueError(f"结构为空: {path}")
    st.remove_waters()
    st.remove_ligands_and_waters()
    return st


def structure_to_clean_pdb(src: Path, dest: Path) -> dict[str, Any]:
    """Remove solvent/ligands and write a Rosetta-friendly PDB."""
    st = _load_structure(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        st.write_pdb(str(dest))
    except Exception:
        st.write_minimal_pdb(str(dest))
    chains = []
    model = st[0]
    for chain in model:
        polymer = chain.get_polymer() if hasattr(chain, "get_polymer") else None
        if polymer is not None and len(polymer) > 0:
            try:
                seq = polymer.make_one_letter_string()
            except Exception:
                seq = ""
            nres = len(polymer)
        else:
            seq = ""
            nres = 0
            for res in chain:
                aa = gemmi_one_letter(res)
                if aa and aa != "X":
                    seq += aa
                    nres += 1
        if nres <= 0:
            continue
        chains.append({"id": chain.name or "A", "length": nres, "sequence": seq})
    if not chains:
        raise ValueError(f"预处理后没有蛋白链: {src}")
    return {"pdb": str(dest), "chains": chains}


def gemmi_one_letter(res) -> str:
    import gemmi

    try:
        return gemmi.find_tabulated_residue(res.name).one_letter_code or "X"
    except Exception:
        return "X"


def detect_antibody_format(
    chains: list[dict[str, Any]],
    *,
    antibody_chains: list[str] | None = None,
    antigen_chains: list[str] | None = None,
) -> dict[str, Any]:
    ids = [c["id"] for c in chains]
    by_id = {c["id"]: c for c in chains}

    def _ok(req: list[str]) -> bool:
        return all(x in by_id for x in req)

    if antibody_chains and antigen_chains and _ok(antibody_chains) and _ok(antigen_chains):
        ab, ag = antibody_chains, antigen_chains
    elif "H" in by_id and "L" in by_id and len(ids) >= 3:
        ab = ["H", "L"]
        ag = [c for c in ids if c not in ab][:1] or [max(ids, key=lambda i: by_id[i]["length"])]
    elif "H" in by_id and len(ids) >= 2:
        ab = ["H"]
        others = [c for c in ids if c != "H"]
        ag = ["A"] if "A" in by_id else others[:1]
    elif len(ids) == 2:
        ordered = sorted(chains, key=lambda c: c["length"])
        short, long = ordered[0], ordered[-1]
        # VHH typically 90–160; antigen usually longer
        if 80 <= short["length"] <= 180:
            ab, ag = [short["id"]], [long["id"]]
        else:
            ab, ag = [ids[0]], [ids[1]]
    elif len(ids) >= 3:
        short = sorted(chains, key=lambda c: c["length"])[:2]
        long = max(chains, key=lambda c: c["length"])
        ab = [c["id"] for c in short if c["id"] != long["id"]][:2]
        ag = [long["id"]]
    else:
        raise ValueError("需要至少两条链（抗体 + 抗原）")

    mode = "vhh" if len(ab) == 1 else "vh_vl"
    interface = f"{''.join(ab)}_{''.join(ag)}"
    return {
        "mode": mode,
        "antibody_chains": ab,
        "antigen_chains": ag,
        "interface": interface,
        "chains": chains,
    }


def _run(cmd: list[str], cwd: Path, log_path: Path, timeout: int = 12 * 3600) -> None:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    log_path.write_text(
        "$ " + " ".join(cmd) + "\n\n" + (proc.stdout or "") + "\n" + (proc.stderr or ""),
        encoding="utf-8",
    )
    if proc.returncode != 0:
        tail = ((proc.stderr or proc.stdout or "")[-2500:]).strip()
        raise RuntimeError(f"{cmd[0]} 失败 (code={proc.returncode}): {tail}")


def _parse_scorefile(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    header: list[str] | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("SCORE:"):
            continue
        parts = line.split()
        if parts[:1] != ["SCORE:"]:
            continue
        cols = parts[1:]
        if header is None or cols[:1] == ["score"] or "description" in cols:
            if "description" in cols or "total_score" in cols or "score" in cols:
                header = cols
                continue
        if not header or len(cols) < 2:
            continue
        rec: dict[str, Any] = {}
        for key, raw in zip(header, cols):
            try:
                rec[key] = float(raw)
            except ValueError:
                rec[key] = raw
        rows.append(rec)
    return rows


def _score_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        val = row.get(key)
        if isinstance(val, (int, float)) and not math.isnan(float(val)):
            return float(val)
    return None


def relax_structure(
    pdb: Path,
    out_dir: Path,
    *,
    relax_bin: Path,
    nstruct: int,
    weights: str = "ref2015",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    scorefile = out_dir / "relax.sc"
    flags = [
        str(relax_bin),
        "-s",
        str(pdb),
        "-relax:fast",
        "-relax:constrain_relax_to_start_coords",
        "-relax:coord_constrain_sidechains",
        "-relax:ramp_constraints",
        "false",
        "-score:weights",
        weights,
        "-use_input_sc",
        "-ex1",
        "-ex2",
        "-flip_HNQ",
        "-no_optH",
        "false",
        "-ignore_unrecognized_res",
        "-nstruct",
        str(max(1, nstruct)),
        "-out:path:pdb",
        str(out_dir),
        "-out:prefix",
        "relax_",
        "-out:file:scorefile",
        str(scorefile),
        "-out:overwrite",
    ]
    (out_dir / "relax.flags.txt").write_text("\n".join(flags) + "\n", encoding="utf-8")
    _run(flags, cwd=out_dir, log_path=out_dir / "relax.log")
    rows = _parse_scorefile(scorefile)
    pdbs = sorted(out_dir.glob("relax_*.pdb"))
    if not pdbs:
        raise RuntimeError(f"FastRelax 未产出 PDB: {out_dir}")
    best_pdb = pdbs[0]
    best_score = None
    if rows:
        ranked = []
        for row in rows:
            score = _score_number(row, "total_score", "score")
            desc = str(row.get("description") or "")
            ranked.append((score if score is not None else 1e9, desc, row))
        ranked.sort(key=lambda x: x[0])
        best_score, desc, _ = ranked[0]
        for pdb_path in pdbs:
            if desc and desc in pdb_path.name:
                best_pdb = pdb_path
                break
        else:
            # SCORE description often matches stem
            by_stem = {p.stem: p for p in pdbs}
            if desc in by_stem:
                best_pdb = by_stem[desc]
    else:
        # fallback: smallest file is not meaningful; keep first
        best_score = None
    shutil.copy2(best_pdb, out_dir / "best.pdb")
    return {
        "best_pdb": str(out_dir / "best.pdb"),
        "nstruct": nstruct,
        "n_models": len(pdbs),
        "total_score": best_score,
        "scorefile": str(scorefile) if scorefile.is_file() else None,
        "models": [p.name for p in pdbs],
    }


def analyze_interface(
    pdb: Path,
    out_dir: Path,
    *,
    analyzer_bin: Path,
    interface: str,
    weights: str = "ref2015",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    scorefile = out_dir / "interface.sc"
    flags = [
        str(analyzer_bin),
        "-s",
        str(pdb),
        "-interface",
        interface,
        "-pack_separated",
        "true",
        "-compute_packstat",
        "true",
        "-add_regular_scores_to_scorefile",
        "-score:weights",
        weights,
        "-ignore_unrecognized_res",
        "-out:file:scorefile",
        str(scorefile),
        "-out:overwrite",
    ]
    (out_dir / "interface.flags.txt").write_text("\n".join(flags) + "\n", encoding="utf-8")
    _run(flags, cwd=out_dir, log_path=out_dir / "interface.log")
    rows = _parse_scorefile(scorefile)
    row = rows[-1] if rows else {}
    metrics = {
        "dG_separated": _score_number(row, "dG_separated"),
        "dG_separated_dSASA": _score_number(row, "dG_separated/dSASAx100", "dG_separated_dSASAx100"),
        "dSASA_int": _score_number(row, "dSASA_int"),
        "dSASA_hphobic": _score_number(row, "dSASA_hphobic"),
        "dSASA_polar": _score_number(row, "dSASA_polar"),
        "hbonds_int": _score_number(row, "hbonds_int"),
        "sc_value": _score_number(row, "sc_value"),
        "packstat": _score_number(row, "packstat"),
        "nres_int": _score_number(row, "nres_int"),
        "fa_rep": _score_number(row, "fa_rep"),
        "complex_normalized": _score_number(row, "complex_normalized"),
        "raw": {k: v for k, v in row.items() if k != "raw"},
    }
    return metrics


def _minmax(values: list[float | None], invert: bool = False) -> list[float]:
    nums = [v for v in values if v is not None and not math.isnan(v)]
    if not nums:
        return [0.0 for _ in values]
    lo, hi = min(nums), max(nums)
    span = hi - lo
    out: list[float] = []
    for v in values:
        if v is None or math.isnan(v):
            out.append(0.0)
            continue
        if span <= 1e-12:
            s = 0.5
        else:
            s = (v - lo) / span
        out.append(1.0 - s if invert else s)
    return out


def rank_variants(rows: list[dict[str, Any]], weights: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """Higher final_score is better. Missing extras are dropped and weights renormalized."""
    default = {
        "interface": 0.35,
        "stability": 0.20,
        "confidence": 0.20,
        "esm2_llr": 0.15,
        "developability": 0.10,
    }
    w = dict(default if weights is None else weights)
    has_conf = any(r.get("confidence") is not None for r in rows)
    has_llr = any(r.get("esm2_llr") is not None for r in rows)
    has_dev = any(r.get("developability") is not None for r in rows)
    if not has_conf:
        w["confidence"] = 0.0
    if not has_llr:
        w["esm2_llr"] = 0.0
    if not has_dev:
        w["developability"] = 0.0
    total_w = sum(w.values()) or 1.0
    w = {k: v / total_w for k, v in w.items()}

    iface = _minmax([r.get("dG_separated") for r in rows], invert=True)  # more negative better
    stab = _minmax([r.get("delta_E") if r.get("delta_E") is not None else r.get("total_score") for r in rows], invert=True)
    conf = _minmax([r.get("confidence") for r in rows], invert=False)
    llr = _minmax([r.get("esm2_llr") for r in rows], invert=False)
    dev = _minmax([r.get("developability") for r in rows], invert=False)

    ranked = []
    for i, row in enumerate(rows):
        score = (
            w["interface"] * iface[i]
            + w["stability"] * stab[i]
            + w["confidence"] * conf[i]
            + w["esm2_llr"] * llr[i]
            + w["developability"] * dev[i]
        )
        item = dict(row)
        item["final_score"] = round(score, 4)
        item["rank_components"] = {
            "interface": round(iface[i], 4),
            "stability": round(stab[i], 4),
            "confidence": round(conf[i], 4),
            "esm2_llr": round(llr[i], 4),
            "developability": round(dev[i], 4),
            "weights": w,
        }
        ranked.append(item)
    ranked.sort(key=lambda r: (-float(r["final_score"]), str(r.get("name") or "")))
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked


def _qc_flags(row: dict[str, Any], wt: dict[str, Any] | None, fa_rep_cut: float = 200.0) -> list[str]:
    flags: list[str] = []
    fa_rep = row.get("fa_rep")
    if isinstance(fa_rep, (int, float)) and fa_rep > fa_rep_cut:
        flags.append("severe_clash")
    if wt:
        wt_sasa = wt.get("dSASA_int")
        sasa = row.get("dSASA_int")
        if isinstance(wt_sasa, (int, float)) and wt_sasa > 1 and isinstance(sasa, (int, float)):
            if sasa < 0.5 * wt_sasa:
                flags.append("unstable_interface")
        wt_h = wt.get("hbonds_int")
        h = row.get("hbonds_int")
        if isinstance(wt_h, (int, float)) and wt_h >= 4 and isinstance(h, (int, float)) and h <= 0:
            flags.append("lost_hbonds")
    if row.get("dG_separated") is None:
        flags.append("missing_interface_energy")
    return flags


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in columns})


def _write_report(path: Path, *, format_info: dict, ranked: list[dict[str, Any]], nstruct: int) -> None:
    lines = [
        "<html><head><meta charset='utf-8'><title>Rosetta 结构评价</title>",
        "<style>body{font-family:sans-serif;margin:24px;color:#23232f} table{border-collapse:collapse;width:100%} td,th{border:1px solid #e0e6ed;padding:6px 8px;font-size:13px} th{background:#e6f7f6}</style>",
        "</head><body>",
        "<h1>Rosetta 抗体–抗原结构评价</h1>",
        f"<p>格式：{format_info.get('mode')} · 界面：{format_info.get('interface')} · 抗体链 {format_info.get('antibody_chains')} · 抗原链 {format_info.get('antigen_chains')} · nstruct={nstruct}</p>",
        "<table><tr>",
    ]
    cols = ["rank", "name", "is_wt", "dG_separated", "ddG", "delta_E", "dSASA_int", "hbonds_int", "sc_value", "final_score", "flags"]
    lines.append("".join(f"<th>{c}</th>" for c in cols) + "</tr>")
    for row in ranked:
        lines.append("<tr>" + "".join(f"<td>{row.get(c, '')}</td>" for c in cols) + "</tr>")
    lines.append("</table></body></html>")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_rosetta_eval_job(
    *,
    work_dir: Path,
    params: dict,
    on_stage: Callable[[str], None] | None = None,
) -> EvalResult:
    t0 = time.time()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    def stage(name: str) -> None:
        if on_stage:
            on_stage(name)

    try:
        stage("prepare")
        backend = resolve_eval_backend(params.get("rosetta_bin_dir"), params.get("pyrosetta_python"))
        if backend.get("reexec") and backend.get("python"):
            params_path = work_dir / "job_params.json"
            payload = dict(params)
            payload.pop("reexec", None)
            params_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            proc = subprocess.run(
                [
                    str(backend["python"]),
                    str(Path(__file__).resolve()),
                    "--work-dir",
                    str(work_dir),
                    "--params-json",
                    str(params_path),
                ],
                capture_output=True,
                text=True,
            )
            (work_dir / "pyrosetta_run.log").write_text(
                (proc.stdout or "") + "\n" + (proc.stderr or ""),
                encoding="utf-8",
            )
            result_path = work_dir / "eval_result.json"
            if result_path.is_file():
                data = json.loads(result_path.read_text(encoding="utf-8"))
                return EvalResult(
                    status=data.get("status", "error"),
                    stage=data.get("stage", "failed"),
                    seconds=float(data.get("seconds") or 0),
                    results=data.get("results") or {},
                    error=data.get("error"),
                )
            raise RuntimeError((proc.stderr or proc.stdout or "PyRosetta 子进程失败")[-4000:])

        nstruct = max(1, min(10, int(params.get("nstruct") or 3)))
        n_jobs = default_n_jobs(params.get("n_jobs"), work_dir=work_dir)
        print(
            f"Rosetta 并行: requested={params.get('n_jobs')!r} → n_jobs={n_jobs} "
            f"(cpu={os.cpu_count()}, variants={len(params.get('variants') or [])}, nstruct={nstruct})",
            flush=True,
        )
        weights = str(params.get("score_weights") or "ref2015")
        variants = list(params.get("variants") or [])
        if not variants:
            raise RuntimeError("没有可评价的结构（需要 WT + 突变体 PDB/CIF）")

        antibody_chains = [c for c in str(params.get("antibody_chains") or "").split() if c]
        antigen_chains = [c for c in str(params.get("antigen_chains") or "").split() if c]
        format_info: dict[str, Any] | None = None
        prepared: list[dict[str, Any]] = []

        for item in variants:
            name = _sanitize_label(str(item.get("name") or Path(item.get("path") or "var").stem))
            src = Path(item["path"])
            if not src.is_file():
                raise RuntimeError(f"找不到结构文件: {src}")
            var_dir = work_dir / "variants" / name
            clean_pdb = var_dir / "input_clean.pdb"
            meta = structure_to_clean_pdb(src, clean_pdb)
            fmt = detect_antibody_format(
                meta["chains"],
                antibody_chains=antibody_chains or None,
                antigen_chains=antigen_chains or None,
            )
            if format_info is None:
                format_info = fmt
            elif fmt["interface"] != format_info["interface"]:
                # keep first detection; still proceed
                pass
            prepared.append(
                {
                    "name": name,
                    "is_wt": bool(item.get("is_wt")),
                    "src": str(src),
                    "clean_pdb": str(clean_pdb),
                    "var_dir": str(var_dir),
                    "confidence": item.get("confidence") or item.get("iptm"),
                    "esm2_llr": item.get("esm2_llr"),
                    "developability": item.get("developability"),
                    "format": fmt,
                }
            )

        if format_info is None:
            raise RuntimeError("无法识别抗体/抗原链")
        (work_dir / "config.resolved.yaml").write_text(
            json.dumps(
                {
                    "mode": format_info["mode"],
                    "antibody_chains": format_info["antibody_chains"],
                    "antigen_chains": format_info["antigen_chains"],
                    "interface": format_info["interface"],
                    "nstruct": nstruct,
                    "n_jobs": n_jobs,
                    "score_weights": weights,
                    "relax_bin": str(backend.get("relax") or ""),
                    "interface_analyzer_bin": str(backend.get("interface_analyzer") or ""),
                    "backend": backend.get("backend"),
                    "pyrosetta_python": backend.get("python"),
                    "protocol": "constrained_fastrelax + InterfaceAnalyzer pack_separated",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        stage("relax")
        if backend.get("backend") == "pyrosetta":
            parallel_relax_pyrosetta(prepared, nstruct=nstruct, weights=weights, n_jobs=n_jobs)
        else:
            for item in prepared:
                var_dir = Path(item["var_dir"])
                relax = relax_structure(
                    Path(item["clean_pdb"]),
                    var_dir / "relax",
                    relax_bin=backend["relax"],
                    nstruct=nstruct,
                    weights=weights,
                )
                item["relax"] = relax
                item["total_score"] = relax.get("total_score")

        stage("interface")
        if backend.get("backend") == "pyrosetta":
            parallel_interface_pyrosetta(
                prepared,
                interface=format_info["interface"],
                weights=weights,
                n_jobs=n_jobs,
            )
        else:
            for item in prepared:
                var_dir = Path(item["var_dir"])
                iface = analyze_interface(
                    Path(item["relax"]["best_pdb"]),
                    var_dir / "interface",
                    analyzer_bin=backend["interface_analyzer"],
                    interface=format_info["interface"],
                    weights=weights,
                )
                item["interface"] = iface

        wt = next((x for x in prepared if x.get("is_wt")), prepared[0])
        wt_dG = (wt.get("interface") or {}).get("dG_separated")
        wt_E = wt.get("total_score")
        wt_iface = wt.get("interface") or {}

        table: list[dict[str, Any]] = []
        for item in prepared:
            iface = item.get("interface") or {}
            dG = iface.get("dG_separated")
            energy = item.get("total_score")
            ddG = None if dG is None or wt_dG is None else dG - wt_dG
            dE = None if energy is None or wt_E is None else energy - wt_E
            row = {
                "name": item["name"],
                "is_wt": bool(item.get("is_wt")),
                "mode": format_info["mode"],
                "interface": format_info["interface"],
                "total_score": energy,
                "dG_separated": dG,
                "ddG": ddG,
                "delta_E": dE,
                "dSASA_int": iface.get("dSASA_int"),
                "hbonds_int": iface.get("hbonds_int"),
                "sc_value": iface.get("sc_value"),
                "packstat": iface.get("packstat"),
                "fa_rep": iface.get("fa_rep"),
                "confidence": item.get("confidence"),
                "esm2_llr": item.get("esm2_llr"),
                "developability": item.get("developability"),
                "best_pdb": item.get("relax", {}).get("best_pdb"),
            }
            row["flags"] = ",".join(_qc_flags(row, wt_iface if not item.get("is_wt") else None))
            table.append(row)

        stage("rank")
        ranked = rank_variants(table)
        columns = [
            "rank",
            "name",
            "is_wt",
            "dG_separated",
            "ddG",
            "delta_E",
            "total_score",
            "dSASA_int",
            "hbonds_int",
            "sc_value",
            "packstat",
            "fa_rep",
            "confidence",
            "esm2_llr",
            "developability",
            "final_score",
            "flags",
        ]
        relaxed_dir = work_dir / "relaxed_structures"
        relaxed_dir.mkdir(parents=True, exist_ok=True)
        for item in prepared:
            best = item.get("relax", {}).get("best_pdb")
            if best and Path(best).is_file():
                shutil.copy2(best, relaxed_dir / f"{item['name']}_relax.pdb")
        _write_csv(work_dir / "scores.csv", ranked, columns)
        _write_csv(work_dir / "ranking.csv", ranked, columns)
        _write_report(work_dir / "report.html", format_info=format_info, ranked=ranked, nstruct=nstruct)
        (work_dir / "summary.json").write_text(
            json.dumps(
                {
                    "format": format_info,
                    "n_variants": len(ranked),
                    "nstruct": nstruct,
                    "ranked": ranked,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        stage("done")
        result = EvalResult(
            status="ok",
            stage="done",
            seconds=round(time.time() - t0, 3),
            results={
                "engine": "rosetta_interface_eval",
                "backend": backend.get("backend"),
                "format": format_info,
                "n_variants": len(ranked),
                "nstruct": nstruct,
                "n_jobs": n_jobs,
                "wt": wt["name"],
                "top": ranked[0] if ranked else None,
                "ranked": ranked,
                "output_files": ["scores.csv", "ranking.csv", "report.html", "summary.json", "config.resolved.yaml"],
            },
        )
        _dump_eval_result(work_dir, result)
        return result
    except Exception as exc:
        stage("failed")
        result = EvalResult(
            status="error",
            stage="failed",
            seconds=round(time.time() - t0, 3),
            results={},
            error=str(exc)[:8000],
        )
        _dump_eval_result(work_dir, result)
        return result


def _dump_eval_result(work_dir: Path, result: EvalResult) -> None:
    (work_dir / "eval_result.json").write_text(
        json.dumps(
            {
                "status": result.status,
                "stage": result.stage,
                "seconds": result.seconds,
                "results": result.results,
                "error": result.error,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Rosetta antibody–antigen evaluation")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--params-json", default="")
    parser.add_argument("--wt", default="", help="WT complex PDB/CIF")
    parser.add_argument("--mutant", nargs="*", default=[], help="Mutant complex files")
    parser.add_argument("--nstruct", type=int, default=3)
    parser.add_argument("--n-jobs", type=int, default=None, help="并行进程数，0/省略 = 自动（尽量吃满 CPU）")
    parser.add_argument("--antibody-chains", default="")
    parser.add_argument("--antigen-chains", default="")
    parser.add_argument("--rosetta-bin", default="")
    parser.add_argument("--pyrosetta-python", default="")
    args = parser.parse_args()
    if args.params_json:
        params = json.loads(Path(args.params_json).read_text(encoding="utf-8"))
    else:
        if not args.wt:
            parser.error("需要 --params-json 或 --wt")
        variants = [{"name": "WT", "path": args.wt, "is_wt": True}]
        for path in args.mutant:
            variants.append({"name": Path(path).stem, "path": path, "is_wt": False})
        params = {
            "variants": variants,
            "nstruct": args.nstruct,
            "n_jobs": args.n_jobs,
            "antibody_chains": args.antibody_chains,
            "antigen_chains": args.antigen_chains,
            "rosetta_bin_dir": args.rosetta_bin or None,
            "pyrosetta_python": args.pyrosetta_python or None,
        }
    result = run_rosetta_eval_job(work_dir=Path(args.work_dir), params=params)
    print(json.dumps({"status": result.status, "error": result.error, "results": result.results}, ensure_ascii=False, indent=2))
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
