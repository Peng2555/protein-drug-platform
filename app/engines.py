"""Structure prediction engine identifiers."""

from __future__ import annotations

FOLD_ENGINES: frozenset[str] = frozenset({"boltz2", "esmfold2"})
MATURATION_ENGINE = "iggm_maturation"
SYNTHESIS_ENGINE = "synthesis_select"
RAS_DOCKING_ENGINE = "ras_tricomplex_docking"
SMALL_MOLECULE_DOCKING_ENGINE = "small_molecule_docking"
DEVELOPABILITY_ENGINE = "esm2_developability"
DESIGN_ENGINE = "protein_mpnn"
ROSETTA_EVAL_ENGINE = "rosetta_interface_eval"
AFFINITY_REDESIGN_ENGINE = "affinity_redesign"
MASKING_PEPTIDE_ENGINE = "masking_peptide"
DEFAULT_FOLD_ENGINE = "boltz2"


def normalize_fold_engine(engine: str | None) -> str:
    val = (engine or DEFAULT_FOLD_ENGINE).strip().lower()
    if val not in FOLD_ENGINES:
        raise ValueError(f"Unsupported fold engine: {engine}")
    return val


def is_fold_engine(engine: str | None) -> bool:
    return (engine or "") in FOLD_ENGINES
