"""第三阶段公共后端模块的隔离单元测试。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from app.common.batch_common import batch_counts, batch_out, batch_status
from app.models import Batch, Job
from app.common.sequence_inputs import (
    parse_fasta_chain_lengths,
    parse_vhh_records,
    save_structure_upload,
)
from app.common.structure_paths import resolve_structure_path
from worker.task_helpers import compact_profile_results, wall_seconds


def test_common_vhh_parser_normalizes_sequences_and_duplicate_ids():
    sequence = "q-" * 70
    records = parse_vhh_records(f">sample note\n{sequence}\n>sample\n{'A' * 70}\n")
    assert records == [("sample", "Q" * 70), ("sample_2", "A" * 70)]


def test_common_chain_parser_keeps_service_specific_constraints():
    assert parse_fasta_chain_lengths(
        ">only\nAAAA\n",
        allowed_chain_ids={"H", "L"},
        extra_chains_error_template="extra: {ids}",
        min_total_length=4,
        too_short_error="short",
    ) == {"H": 4}

    with pytest.raises(HTTPException) as exc:
        parse_fasta_chain_lengths(
            ">H\nAAAA\n>L\nAAAA\n",
            allowed_chain_ids={"H"},
            extra_chains_error_template="只接受 H：{ids}",
            min_total_length=4,
            too_short_error="short",
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "只接受 H：L"


def test_common_structure_upload_normalizes_mmcif(tmp_path: Path):
    upload = UploadFile(filename="input.mmcif", file=BytesIO(b"x" * 80))
    saved = asyncio.run(save_structure_upload(upload, tmp_path / "structure.mmcif"))
    assert saved == tmp_path / "structure.cif"
    assert saved.read_bytes() == b"x" * 80


def test_batch_common_counts_status_and_response(sqlite_sessions, active_user):
    with sqlite_sessions() as db:
        batch = Batch(
            user_id=active_user.id,
            name="common-batch",
            batch_type="tnp_profile",
            target_name="",
            target_chain_id="",
            target_sequence="",
            heavy_chain_id="H",
            heavy_chain_count=3,
            use_msa_server=True,
        )
        db.add(batch)
        db.flush()
        for status in ("done", "failed", "cancelled"):
            db.add(
                Job(
                    user_id=active_user.id,
                    name=status,
                    engine="tnp_profile",
                    status=status,
                    batch_id=batch.id,
                    fasta_text=">H\nAAAA\n",
                    sequence_hash=status,
                    chains_json={"H": 4},
                    total_length=4,
                    use_msa_server=True,
                )
            )
        db.flush()

        counts = batch_counts(db, batch.id)
        assert counts == {
            "done": 1,
            "running": 0,
            "queued": 0,
            "failed": 1,
            "cancelled": 1,
        }
        assert batch_status(counts, 3) == "partial"
        output = batch_out(batch, db)
        assert output.status == "partial"
        assert output.done_count == output.failed_count == output.cancelled_count == 1


def test_structure_path_resolution_and_md_export(tmp_path: Path):
    from app.modules.md.service import resolve_structure_path as md_export

    structure = tmp_path / "pred.cif"
    structure.write_text("data_test", encoding="utf-8")
    parent = Job(id="parent", structure_path=str(structure))
    assert resolve_structure_path(parent) == structure
    assert md_export(parent) == structure


def test_worker_helpers_handle_naive_time_and_compact_results():
    started = datetime(2026, 1, 1)
    finished = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=4)
    assert wall_seconds(started, finished) == 4
    assert compact_profile_results(
        {"summary": {"ok": True}, "pred_cif": "pred.cif", "patches": [{}, {}]},
        include_patch_count=True,
    ) == {"summary": {"ok": True}, "pred_cif": "pred.cif", "n_patches": 2}


def test_engine_and_celery_compatibility_surfaces_remain_stable():
    from app.engines import GROMACS_MD_ENGINE
    from app.modules.hydro_redesign.service import save_structure_upload as hydro_upload
    from app.common.sequence_inputs import save_structure_upload as common_upload
    from app.modules.tnp_profile.service import save_structure_upload as tnp_upload
    from worker import tasks

    assert GROMACS_MD_ENGINE == "gromacs_md"
    assert hydro_upload is common_upload
    assert tnp_upload is common_upload
    assert tasks.run_md_job.name == "worker.tasks.run_md_job"
    assert tasks.run_rosetta_eval_job.name == "worker.tasks.run_rosetta_eval_job"
