"""抗体改造项目阶段一：模型、迁移、存储与溯源基础测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.core.config import ROOT, settings
from app.core.models import User
from app.modules.antibody_projects.models import (
    AntibodyCandidate,
    AntibodyProject,
    AntibodyVersion,
    AntibodyVersionChain,
    AuditEvent,
    ExperimentMeasurement,
    ExperimentRecord,
    ProjectMember,
    ProjectRole,
    SampleBatch,
    VersionMutation,
)
from app.modules.antibody_projects.provenance import (
    normalize_sequence,
    protein_and_optional_cds,
    sequence_sha256,
    translate_cds,
    version_sha256,
)
from app.modules.antibody_projects.storage import project_storage_dir, sha256_file


ANTIBODY_TABLES = {
    "antibody_projects",
    "antibody_project_members",
    "antibody_candidates",
    "antibody_versions",
    "antibody_version_chains",
    "antibody_version_mutations",
    "antibody_sample_batches",
    "antibody_experiments",
    "antibody_experiment_measurements",
    "antibody_project_job_links",
    "antibody_project_artifacts",
    "antibody_audit_events",
}


def test_model_metadata_contains_antibody_foundation() -> None:
    from app.core.database import Base

    assert ANTIBODY_TABLES.issubset(Base.metadata.tables)


def test_project_lineage_experiment_and_audit_round_trip(sqlite_sessions, active_user) -> None:
    with sqlite_sessions() as db:
        project = AntibodyProject(
            owner_id=active_user.id,
            project_code="EGFR-001",
            name="EGFR 抗体优化",
            target_name="EGFR",
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectMember(
                project_id=project.id,
                user_id=active_user.id,
                role=ProjectRole.owner.value,
            )
        )
        candidate = AntibodyCandidate(
            project_id=project.id,
            candidate_code="AB-A",
            name="候选抗体 A",
            antibody_type="igg",
            created_by=active_user.id,
        )
        db.add(candidate)
        db.flush()

        wt_hash = version_sha256({"VH": "QVQLVQ", "VL": "DIQMTQ"})
        wt = AntibodyVersion(
            candidate_id=candidate.id,
            version_code="WT",
            version_number=0,
            sequence_hash=wt_hash,
            created_by=active_user.id,
            status="locked",
        )
        db.add(wt)
        db.flush()
        db.add_all(
            [
                AntibodyVersionChain(
                    version_id=wt.id,
                    chain_role="VH",
                    variable_sequence="QVQLVQ",
                    sequence_hash=sequence_sha256("QVQLVQ"),
                ),
                AntibodyVersionChain(
                    version_id=wt.id,
                    chain_role="VL",
                    variable_sequence="DIQMTQ",
                    sequence_hash=sequence_sha256("DIQMTQ"),
                ),
            ]
        )

        m1 = AntibodyVersion(
            candidate_id=candidate.id,
            primary_parent_id=wt.id,
            version_code="M1",
            version_number=1,
            name="CDR-H3 优化",
            sequence_hash=version_sha256({"VH": "QVQLVW", "VL": "DIQMTQ"}),
            created_by=active_user.id,
        )
        db.add(m1)
        db.flush()
        db.add(
            VersionMutation(
                version_id=m1.id,
                parent_version_id=wt.id,
                chain_role="VH",
                mutation_type="substitution",
                sequence_position=6,
                from_aa="Q",
                to_aa="W",
                rationale="提高结合能力",
            )
        )
        sample = SampleBatch(
            version_id=m1.id,
            batch_code="EXP-001",
            expression_date=date(2026, 9, 16),
            concentration_value=2.1,
            concentration_unit="mg/mL",
            operator_id=active_user.id,
        )
        db.add(sample)
        db.flush()
        experiment = ExperimentRecord(
            project_id=project.id,
            version_id=m1.id,
            sample_batch_id=sample.id,
            title="SPR 亲和力",
            experiment_type="affinity",
            experiment_date=date(2026, 9, 16),
            operator_id=active_user.id,
        )
        db.add(experiment)
        db.flush()
        db.add_all(
            [
                ExperimentMeasurement(
                    experiment_id=experiment.id,
                    metric_name="KD",
                    value_numeric=1.2,
                    unit="nM",
                ),
                AuditEvent(
                    project_id=project.id,
                    entity_type="antibody_version",
                    entity_id=m1.id,
                    action="create",
                    actor_id=active_user.id,
                    after_json={"version_code": "M1"},
                ),
            ]
        )
        db.commit()

        stored = db.scalar(
            select(AntibodyVersion).where(
                AntibodyVersion.candidate_id == candidate.id,
                AntibodyVersion.version_code == "M1",
            )
        )
        assert stored is not None
        assert stored.primary_parent_id == wt.id
        assert db.scalar(select(ExperimentMeasurement)).unit == "nM"
        assert db.scalar(select(AuditEvent)).after_json == {"version_code": "M1"}


def test_sequence_fingerprints_are_canonical() -> None:
    assert normalize_sequence(" qvql\nvq ") == "QVQLVQ"
    protein = (
        "EVQLVESGGGLVQPGGSLRLSCEASGFTFSNHGMSWVRQAQGKGLEWVAKVKRDGTEKYYVDSVRG"
        "RFTISRDNAKNSLYLQMNSLRAEDTAVYYCVRDVDYDFRRNDYYGLEIWAQGTTVTVSS"
    )
    assert len(protein) == 125
    assert normalize_sequence(protein + "GAG" * 125) == protein
    assert translate_cds("ATG" * 20) == "M" * 20
    protein_from_dna, cds = protein_and_optional_cds("aug" * 20)
    assert protein_from_dna == "M" * 20
    assert cds == "ATG" * 20
    try:
        normalize_sequence("ATG" * 20 + "AT")
    except ValueError as exc:
        assert "3 的倍数" in str(exc)
    else:
        raise AssertionError("partial codon DNA should be rejected")
    assert sequence_sha256("qvqlvq") == sequence_sha256(" QVQLVQ\n")
    assert version_sha256({"VL": "DIQMTQ", "VH": "QVQLVQ"}) == version_sha256(
        {"VH": "QVQLVQ", "VL": "DIQMTQ"}
    )


def test_storage_uses_uuid_directory_and_sha256(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "antibody_projects_out_root", tmp_path)
    project_id = "37e20c72-4c44-49da-b506-f2f326f31115"
    project_dir = project_storage_dir(project_id)
    artifact = project_dir / "result.txt"
    artifact.write_text("antibody-result", encoding="utf-8")

    assert project_dir == tmp_path / project_id
    assert sha256_file(artifact) == (
        "8bb9e58f7998280201a2dcd846753ed0578186f13588c7207ca57ec397b0c6e2"
    )


def test_alembic_upgrade_preserves_legacy_rows(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setattr(settings, "database_url", database_url)
    alembic_config = Config(str(ROOT / "alembic.ini"))

    command.upgrade(alembic_config, "0001_legacy_schema")
    migration_engine = create_engine(database_url)
    factory = sessionmaker(bind=migration_engine)
    with factory() as db:
        db.add(
            User(
                username="legacy-user",
                email="legacy@example.test",
                password_hash="not-used",
            )
        )
        db.commit()

    command.upgrade(alembic_config, "head")
    with factory() as db:
        assert db.scalar(select(User).where(User.username == "legacy-user")) is not None
    assert ANTIBODY_TABLES.issubset(inspect(migration_engine).get_table_names())
    migration_engine.dispose()
