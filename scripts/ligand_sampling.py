"""ETKDGv3 ligand start sampling for Web docking.

Input coordinates are never used. The molecular graph comes from SMILES
(or InChI); every start is embedded afresh, optimized, clustered, then
selected as a docking seed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Sequence

from rdkit import Chem
from rdkit.Chem import AllChem, TorsionFingerprints
from rdkit.ML.Cluster import Butina


@dataclass
class ConformerEnsemble:
    molecule: Chem.Mol
    energies: list[float]
    force_field: str
    geometry_hashes: list[str]
    clusters: list[tuple[int, ...]]
    cluster_method: str
    optimization_statuses: list[int]


@dataclass
class SampledStarts:
    smiles: str
    canonical_smiles: str
    ensemble: ConformerEnsemble
    starts: list[dict]


def parse_ligand_query(text: str) -> Chem.Mol:
    """Parse a SMILES or InChI string into a coordinate-free graph."""

    query = (text or "").strip()
    if not query:
        raise ValueError("请填写小分子 SMILES（结构式），不能只给分子式")
    first_line = query.splitlines()[0].strip()
    token = first_line.split()[0]
    if token.lower().startswith("inchi="):
        mol = Chem.MolFromInchi(token)
    else:
        mol = Chem.MolFromSmiles(token)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError(
            "无法解析该结构式。请填写 SMILES（例如 CCO），"
            "不要填写分子式（例如 C2H6O）"
        )
    if mol.GetNumHeavyAtoms() < 3:
        raise ValueError("配体重原子数过少，无法对接")
    if mol.GetNumHeavyAtoms() > 200:
        raise ValueError("配体过大（>200 个重原子），请缩小结构后再试")
    mol = Chem.RemoveHs(mol, sanitize=True)
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    mol.RemoveAllConformers()
    _assign_atom_maps(mol)
    mol.SetProp("_Name", "ligand")
    return mol


def _assign_atom_maps(mol: Chem.Mol) -> None:
    map_number = 1
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 1:
            continue
        atom.SetAtomMapNum(map_number)
        map_number += 1


def stereochemistry_signature(mol: Chem.Mol) -> tuple[tuple[int, str], ...]:
    probe = Chem.Mol(mol)
    Chem.AssignStereochemistry(probe, cleanIt=False, force=True)
    return tuple(
        sorted(
            (atom.GetAtomMapNum(), atom.GetProp("_CIPCode"))
            for atom in probe.GetAtoms()
            if atom.GetAtomMapNum() and atom.HasProp("_CIPCode")
        )
    )


def _geometry_hash(mol: Chem.Mol, conf_id: int) -> str:
    graph = Chem.MolToSmiles(Chem.RemoveHs(mol), isomericSmiles=True)
    conf = mol.GetConformer(conf_id)
    heavy = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() != 1]
    distances = []
    for pos, first in enumerate(heavy):
        p1 = conf.GetAtomPosition(first)
        for second in heavy[pos + 1 :]:
            p2 = conf.GetAtomPosition(second)
            distances.append(f"{p1.Distance(p2):.3f}")
    payload = graph + "|" + ",".join(distances)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _optimize(mol: Chem.Mol, max_iterations: int) -> tuple[str, list[tuple[int, float]]]:
    if AllChem.MMFFHasAllMoleculeParams(mol):
        values = AllChem.MMFFOptimizeMoleculeConfs(
            mol, numThreads=1, maxIters=max_iterations, mmffVariant="MMFF94s",
        )
        return "MMFF94s", [(int(status), float(energy)) for status, energy in values]
    if not AllChem.UFFHasAllMoleculeParams(mol):
        raise RuntimeError("该分子既不能用 MMFF94s 也不能用 UFF 优化")
    values = AllChem.UFFOptimizeMoleculeConfs(mol, numThreads=1, maxIters=max_iterations)
    return "UFF", [(int(status), float(energy)) for status, energy in values]


def _copy_selected_conformers(mol: Chem.Mol, selected: Sequence[int]) -> Chem.Mol:
    copied = Chem.Mol(mol)
    copied.RemoveAllConformers()
    for old_id in selected:
        copied.AddConformer(Chem.Conformer(mol.GetConformer(old_id)), assignId=True)
    return copied


def _cluster_conformers(
    mol: Chem.Mol, *, tfd_cutoff: float, rmsd_cutoff: float,
) -> tuple[list[tuple[int, ...]], str]:
    count = mol.GetNumConformers()
    if count == 1:
        return [(0,)], "single"
    try:
        distances = list(TorsionFingerprints.GetTFDMatrix(mol))
        if distances and all(value == value for value in distances):
            clusters = Butina.ClusterData(
                distances, count, tfd_cutoff, isDistData=True, reordering=True,
            )
            return [tuple(cluster) for cluster in clusters], "TFD"
    except (IndexError, ValueError, ZeroDivisionError):
        pass
    heavy = Chem.RemoveHs(mol)
    distances = list(AllChem.GetConformerRMSMatrix(heavy, prealigned=False))
    clusters = Butina.ClusterData(
        distances, count, rmsd_cutoff, isDistData=True, reordering=True,
    )
    return [tuple(cluster) for cluster in clusters], "RMSD"


def generate_conformer_ensemble(
    molecule: Chem.Mol,
    *,
    num_conformers: int = 128,
    random_seed: int = 0xC0FFEE,
    max_iterations: int = 1000,
    tfd_cutoff: float = 0.02,
    rmsd_cutoff: float = 1.5,
) -> ConformerEnsemble:
    if num_conformers < 1:
        raise ValueError("构象采样数必须为正")
    expected_stereo = stereochemistry_signature(molecule)
    mol = Chem.AddHs(Chem.Mol(molecule), addCoords=False)
    mol.RemoveAllConformers()
    params = AllChem.ETKDGv3()
    params.randomSeed = int(random_seed)
    params.useMacrocycleTorsions = True
    params.useMacrocycle14config = True
    params.enforceChirality = True
    params.clearConfs = True
    params.pruneRmsThresh = -1.0
    params.numThreads = 1
    conformer_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=num_conformers, params=params))
    if not conformer_ids:
        raise RuntimeError("ETKDGv3 未能生成任何构象")
    force_field, optimized = _optimize(mol, max_iterations)
    seen: set[str] = set()
    selected: list[int] = []
    energies: list[float] = []
    statuses: list[int] = []
    hashes: list[str] = []
    for conf_id, (status, energy) in zip(conformer_ids, optimized):
        digest = _geometry_hash(mol, conf_id)
        if digest in seen:
            continue
        seen.add(digest)
        selected.append(conf_id)
        energies.append(energy)
        statuses.append(status)
        hashes.append(digest)
    unique = _copy_selected_conformers(mol, selected)
    if stereochemistry_signature(Chem.RemoveHs(unique)) != expected_stereo:
        raise RuntimeError("采样过程中立体化学发生了变化")
    clusters, method = _cluster_conformers(unique, tfd_cutoff=tfd_cutoff, rmsd_cutoff=rmsd_cutoff)
    return ConformerEnsemble(
        molecule=unique,
        energies=energies,
        force_field=force_field,
        geometry_hashes=hashes,
        clusters=clusters,
        cluster_method=method,
        optimization_statuses=statuses,
    )


def select_start_conformers(ensemble: ConformerEnsemble, n_starts: int) -> dict[int, int]:
    """Pick the N lowest-energy cluster representatives as docking starts."""

    if n_starts < 1:
        raise ValueError("起点数必须为正")
    ordered_clusters = sorted(
        ensemble.clusters,
        key=lambda cluster: min(ensemble.energies[index] for index in cluster),
    )
    representatives = [
        min(cluster, key=lambda index: (ensemble.energies[index], index))
        for cluster in ordered_clusters
    ]
    chosen = representatives[: min(n_starts, len(representatives))]
    return {seed: conf_index for seed, conf_index in enumerate(chosen)}


def write_start_sdf(
    path: Path,
    ensemble: ConformerEnsemble,
    *,
    conformer_index: int,
    seed: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = Chem.Mol(ensemble.molecule)
    record.SetProp("_Name", f"ligand__seed_{seed}")
    record.SetProp("seed", str(seed))
    record.SetProp("conformer_index", str(conformer_index))
    record.SetProp("geometry_hash", ensemble.geometry_hashes[conformer_index])
    record.SetProp("force_field", ensemble.force_field)
    record.SetProp("energy", f"{ensemble.energies[conformer_index]:.8f}")
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = Chem.SDWriter(handle)
        writer.write(record, confId=conformer_index)
        writer.close()


def sample_starts_from_smiles(
    smiles: str,
    output_dir: Path,
    *,
    n_starts: int = 10,
    n_conformers: int = 128,
    generation_seed: int = 0xC0FFEE,
    tfd_cutoff: float = 0.02,
) -> SampledStarts:
    graph = parse_ligand_query(smiles)
    unlabeled = Chem.Mol(graph)
    for atom in unlabeled.GetAtoms():
        atom.SetAtomMapNum(0)
    canonical = Chem.MolToSmiles(unlabeled, isomericSmiles=True)
    ensemble = generate_conformer_ensemble(
        graph,
        num_conformers=n_conformers,
        random_seed=generation_seed,
        tfd_cutoff=tfd_cutoff,
    )
    selected = select_start_conformers(ensemble, n_starts)
    starts: list[dict] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for seed, conformer_index in selected.items():
        path = output_dir / f"start_seed_{seed}.sdf"
        write_start_sdf(path, ensemble, conformer_index=conformer_index, seed=seed)
        starts.append({
            "seed": seed,
            "conformer_index": conformer_index,
            "geometry_hash": ensemble.geometry_hashes[conformer_index],
            "energy": ensemble.energies[conformer_index],
            "sdf": str(path),
        })
    return SampledStarts(
        smiles=smiles.strip(),
        canonical_smiles=canonical,
        ensemble=ensemble,
        starts=starts,
    )
