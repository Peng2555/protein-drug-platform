"""Compatibility contracts for the public ``app.schemas`` facade."""

from __future__ import annotations

import hashlib
import importlib
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app
import app.modules
import app.schemas as schemas


# Frozen from safety/pre-app-restructure-20260915-1637:app/schemas.py.
PUBLIC_SCHEMA_NAMES = (
    "UserCreate", "UserLogin", "UserOut", "RegisterOut", "TokenOut",
    "ChainInput", "EsmFold2Params", "Boltz2Params", "BoltzModification",
    "BoltzComponent", "BoltzPocketConstraint", "BoltzContactConstraint",
    "BoltzAffinity", "JobCreate", "JobOut", "MdJobCreate", "MdJobOut",
    "MdJobListOut", "RasDockingJobCreate", "RasDockingJobOut",
    "RasDockingJobListOut", "DockingJobCreate", "DockingJobOut",
    "DockingJobListOut", "DevelopabilityJobCreate", "DevelopabilityJobOut",
    "DevelopabilityJobListOut", "DesignJobCreate", "DesignJobOut",
    "DesignJobListOut", "RosettaEvalJobCreate", "RosettaEvalJobOut",
    "RosettaEvalJobListOut", "AffinityRedesignJobCreate",
    "AffinityRedesignJobOut", "AffinityRedesignJobListOut",
    "AffinityRedesignRankedOut", "MaskingPeptideJobCreate",
    "MaskingPeptideJobOut", "MaskingPeptideJobListOut",
    "MaskingPeptideSequencesOut", "HydroRedesignJobCreate",
    "HydroRedesignBatchCreate", "HydroRedesignJobOut",
    "HydroRedesignJobListOut", "HydroRedesignProgressOut",
    "HydroRedesignRankedOut", "HydroRedesignBatchCreateOut",
    "CicProfileJobCreate", "CicProfileJobOut", "CicProfileJobListOut",
    "CicProfileProgressOut", "CicProfileRankedOut", "TnpProfileJobCreate",
    "TnpProfileBatchCreate", "TnpProfileJobOut", "TnpProfileJobListOut",
    "TnpProfileProgressOut", "TnpProfileRankedOut", "IgGMParams",
    "MaturationJobCreate", "MaturationJobOut", "MaturationJobListOut",
    "MaturationVariantOut", "MaturationVariantsOut", "MaturationLogSection",
    "MaturationLogsOut", "AffinityRedesignProgressOut",
    "SynthesisSelectParams", "SynthesisSelectOut", "SynthesisCandidateOut",
    "SynthesisCandidatesOut", "SynthesisJobOut", "SynthesisJobListOut",
    "JobListOut", "HealthOut", "CdrSpanOut", "SequenceSegmentOut",
    "ResidueOut", "ChainSequenceOut", "JobSequencesOut",
    "InterfaceResidueOut", "InterfaceInteractionOut",
    "InterfaceInteractionSummaryOut", "InterfacePairOut", "InterfaceChainOut",
    "InterfaceReferenceToolOut", "JobInterfaceOut", "TargetInput",
    "HeavyChainInput", "VhhPanelCreate", "AntibodyInput",
    "AntibodyOnlyCreate", "BatchJobOut", "BatchOut", "BatchDetailOut",
    "BatchJobsListOut", "BatchListOut", "VhhPanelCreateOut",
    "TnpProfileBatchCreateOut", "HeavyCsvParseRow", "HeavyCsvParseOut",
    "HeavyCsvParseB64", "AntibodyParseRow", "AntibodyParseOut",
)

SCHEMA_SHA256 = {
    "UserCreate": "1cc74578105cb2676c450b0de96d383476b10d39c8680747dfd5a37d9c7cd2e5",
    "Boltz2Params": "4c0e65f65f1fcd9d262a8f536da724b60c7dfa0edc73bb5580e2ade2b4d402d7",
    "BoltzComponent": "ddba74578ec272d38f03161db4147921251ffb2c295285a7c94a28b27733b855",
    "JobCreate": "e037fdb82087944fc1d47750f331e52ff4392f435640c96dcbf42bc038e712ac",
    "JobOut": "fc678d0a32fac2085e78d6db358c6aeb47b83c0a4f317c33391ea7fac96fff24",
    "DockingJobCreate": "b4f201e4d5bac8b1fb788736f443272ce8dedee5f06833e7df14847a9ec80ed1",
    "MaturationJobCreate": "ca047ac81396bcc189926c9d705db03a81e4bcac1906d59040b476e7e725aeb4",
    "SynthesisCandidateOut": "1c34166e7ae9fcc5cf5f92047a77084722faca498868e1991637a6cf911f79b9",
    "BatchOut": "f6e74f24c646143b8fbb63b9d1ace52f39a46379c2a06c9f9d5ecb7d145b6555",
    "VhhPanelCreate": "a9c863b5ff86fb666fa842f3303b18e553b60d8362423bf0c3f3918adb819d3c",
    "HydroRedesignJobCreate": "8f2e66db12ed312718aed99562c88db24ee111880a099e2bf02413749ff92032",
    "TnpProfileRankedOut": "98450234db66fbc7599067cafe139250b3dc02cd7afc34914b43342daea073fe",
    "JobInterfaceOut": "07b88140393356e55812b87a6bb2a080f65c706b61fbd367e9a8bc366291639d",
}


def _schema_digest(model: type) -> str:
    payload = json.dumps(
        model.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def test_public_schema_names_are_frozen() -> None:
    assert frozenset(schemas.__all__) == frozenset(PUBLIC_SCHEMA_NAMES)
    assert len(schemas.__all__) == len(PUBLIC_SCHEMA_NAMES)
    assert all(getattr(schemas, name) is not None for name in PUBLIC_SCHEMA_NAMES)


@pytest.mark.parametrize(("name", "digest"), SCHEMA_SHA256.items())
def test_key_json_schemas_match_frozen_contract(name: str, digest: str) -> None:
    model = getattr(schemas, name)
    assert list(model.model_fields) == list(model.model_json_schema()["properties"])
    assert _schema_digest(model) == digest


def test_defaults_and_response_serialization_are_unchanged() -> None:
    assert schemas.Boltz2Params().model_dump() == {
        "recycling_steps": 3, "sampling_steps": 200, "diffusion_samples": 1,
        "max_parallel_samples": 5, "step_scale": None, "seed": None,
        "output_format": "mmcif", "model": "boltz2", "method": None,
        "use_potentials": False, "use_msa_server": True,
        "msa_pairing_strategy": "greedy", "max_msa_seqs": 8192,
        "subsample_msa": False, "num_subsampled_msa": 1024,
        "write_full_pae": False, "write_full_pde": False,
        "write_embeddings": False,
    }
    assert schemas.MaskingPeptideJobCreate().hotspot_res == [
        "H35", "H47", "H50", "H104", "H110",
    ]
    source = SimpleNamespace(
        id="u1", username="alice", email=None, created_at=datetime(2026, 1, 2),
    )
    assert schemas.UserOut.model_validate(source).model_dump(mode="json") == {
        "id": "u1", "username": "alice", "email": None, "is_active": True,
        "is_admin": False, "created_at": "2026-01-02T00:00:00",
    }


def test_model_validators_are_unchanged() -> None:
    component = schemas.BoltzComponent(ids=[" H "], sequence=" aa\n")
    assert component.ids == ["H"]
    assert component.sequence == "AA"
    with pytest.raises(ValidationError, match="配体需且仅需提供"):
        schemas.BoltzComponent(entity="ligand", ids=["L"])
    with pytest.raises(ValidationError, match="亲和力 binder"):
        schemas.JobCreate(
            components=[
                {"entity": "protein", "ids": ["A"], "sequence": "AA"},
                {"entity": "ligand", "ids": ["L"], "ccd": "ATP"},
            ],
            affinity={"binder": "X"},
        )
    with pytest.raises(ValidationError, match="必须提供 FASTA"):
        schemas.MaturationJobCreate(structure_source="boltz2")


def test_all_router_and_service_modules_import() -> None:
    app_dir = Path(app.__file__).parent
    router_modules = [
        ".".join(path.with_suffix("").relative_to(app_dir.parent).parts)
        for path in (app_dir / "modules").glob("*/router.py")
    ]
    service_modules = [
        ".".join(path.with_suffix("").relative_to(app_dir.parent).parts)
        for path in (app_dir / "modules").glob("*/service.py")
    ]
    for module_name in sorted(router_modules + service_modules):
        importlib.import_module(module_name)
