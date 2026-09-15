"""第二阶段 app/common 搬迁的导入、身份与行为契约。"""

from __future__ import annotations

import importlib
from pathlib import Path

from app.common.batch_common import batch_status
from app.common.cdr_annotation import build_chain_display
from app.common.csv_decode import decode_upload_bytes, parse_heavy_chain_text
from app.common.job_paths import job_output_dir, job_output_dir_name
from app.common.sequence_inputs import parse_vhh_records
from app.common.structure_paths import resolve_structure_path
from app.common.vhh_panel import HeavyChainSpec, TargetSpec, prepare_panel_jobs
from app.models import Job


COMMON_MODULES = (
    "antibody_only",
    "batch_common",
    "cdr_annotation",
    "csv_decode",
    "job_paths",
    "sequence_inputs",
    "structure_paths",
    "vhh_panel",
)


def test_common_modules_import_only_from_new_package():
    for name in COMMON_MODULES:
        assert importlib.import_module(f"app.common.{name}").__name__ == f"app.common.{name}"
        assert not (Path(__file__).parents[1] / "app" / f"{name}.py").exists()


def test_callers_retain_common_helper_identity():
    from app.common.cdr_annotation import annotate_fasta
    from app.common.sequence_inputs import save_structure_upload
    from app.modules.fold.interface import annotate_fasta as interface_annotate_fasta
    from app.modules.md.service import resolve_structure_path as md_resolve_structure_path
    from app.modules.tnp_profile.service import save_structure_upload as tnp_save_structure_upload

    assert interface_annotate_fasta is annotate_fasta
    assert md_resolve_structure_path is resolve_structure_path
    assert tnp_save_structure_upload is save_structure_upload


def test_fasta_batch_and_structure_path_behavior(tmp_path: Path):
    sequence = "q-" * 70
    assert parse_vhh_records(f">sample\n{sequence}\n>sample\n{'A' * 70}\n") == [
        ("sample", "Q" * 70),
        ("sample_2", "A" * 70),
    ]
    assert batch_status(
        {"done": 1, "running": 0, "queued": 0, "failed": 1, "cancelled": 0},
        2,
    ) == "partial"

    structure = tmp_path / "pred.cif"
    structure.write_text("data_contract", encoding="utf-8")
    assert resolve_structure_path(Job(id="job", structure_path=str(structure))) == structure


def test_csv_decode_and_job_path_behavior(tmp_path: Path):
    text, encoding = decode_upload_bytes(
        b"vhh_id,sequence\nsample,QVQLQESGGGLVQPGGSLRLSCAASG\n",
        "panel.csv",
    )
    assert encoding == "UTF-8"
    assert parse_heavy_chain_text(text) == (
        [("sample", "QVQLQESGGGLVQPGGSLRLSCAASG")],
        "csv",
    )
    assert job_output_dir_name(" demo job ", "12345678-abcd", {"H": 70}) == "demo_job__12345678"
    assert job_output_dir(tmp_path, " demo job ", "12345678-abcd") == tmp_path / "demo_job__12345678"


def test_cdr_display_and_vhh_panel_entry_behavior():
    assert build_chain_display(
        "ABCDE",
        [{"name": "CDR-H1", "start": 1, "end": 2}],
    ) == [
        {"type": "fw", "text": "A"},
        {"type": "cdr", "name": "CDR-H1", "text": "BC"},
        {"type": "fw", "text": "DE"},
    ]

    batch, target, jobs, skipped = prepare_panel_jobs(
        batch_name="panel demo",
        target_name="target",
        target_chain_id="A",
        target_sequence="A" * 20,
        heavy_chain_id="H",
        heavy_chains=[
            HeavyChainSpec(id="VHH1", sequence="Q" * 20),
            HeavyChainSpec(id="VHH2", sequence="Q" * 20),
        ],
    )
    assert batch == "panel_demo"
    assert target == TargetSpec(name="target", chain_id="A", sequence="A" * 20)
    assert jobs == [("target_VHH1", "VHH1", f">H\n{'Q' * 20}\n>A\n{'A' * 20}\n")]
    assert skipped == 1
