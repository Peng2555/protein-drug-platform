"""Contracts for the app/core move and centralized router registry."""

from __future__ import annotations

import importlib
from pathlib import Path

from app.core import config
from app.core.celery import celery_app
from app.core.models import Batch, Job, User
from app.modules import ROUTERS


ROOT = Path(__file__).resolve().parents[1]

ROUTER_MODULES = (
    "app.modules.auth.router",
    "app.modules.fold.router",
    "app.modules.fold.batch_router",
    "app.modules.md.router",
    "app.modules.maturation.router",
    "app.modules.synthesis.router",
    "app.modules.ras_docking.router",
    "app.modules.docking.router",
    "app.modules.developability.router",
    "app.modules.design.router",
    "app.modules.rosetta_eval.router",
    "app.modules.affinity_redesign.router",
    "app.modules.masking_peptide.router",
    "app.modules.hydro_redesign.router",
    "app.modules.cic_profile.router",
    "app.modules.tnp_profile.router",
)

TASK_NAMES = {
    "worker.tasks.run_fold_job",
    "worker.tasks.run_md_job",
    "worker.tasks.run_maturation_job",
    "worker.tasks.run_ras_docking_job",
    "worker.tasks.run_small_molecule_docking_job",
    "worker.tasks.run_developability_job",
    "worker.tasks.run_design_job",
    "worker.tasks.run_rosetta_eval_job",
    "worker.tasks.run_affinity_redesign_job",
    "worker.tasks.run_masking_peptide_job",
    "worker.tasks.run_hydro_redesign_job",
    "worker.tasks.run_cic_profile_job",
    "worker.tasks.run_tnp_profile_job",
}


def test_config_root_and_key_defaults_are_unchanged() -> None:
    assert config.ROOT == ROOT
    fields = config.Settings.model_fields
    assert fields["database_url"].default == f"sqlite:///{ROOT / 'data' / 'boltzfold.db'}"
    assert fields["redis_url"].default == "redis://127.0.0.1:6380/0"
    assert fields["access_token_expire_minutes"].default == 60 * 24 * 7
    assert fields["celery_gpu_count"].default == 4
    assert fields["celery_gpu_queue"].default == "gpu"
    assert fields["boltz2_out_root"].default == ROOT / "outputs"
    assert fields["md_out_root"].default == ROOT / "md_outputs"
    assert fields["antibody_redesign_root"].default == ROOT


def test_sqlalchemy_table_and_column_contracts_are_unchanged() -> None:
    assert {
        model.__tablename__: tuple(model.__table__.columns.keys())
        for model in (User, Batch, Job)
    } == {
        "users": (
            "id", "username", "email", "password_hash", "is_active", "is_admin",
            "created_at",
        ),
        "batches": (
            "id", "user_id", "name", "batch_type", "target_name",
            "target_chain_id", "target_sequence", "heavy_chain_id",
            "heavy_chain_count", "use_msa_server", "created_at",
        ),
        "jobs": (
            "id", "user_id", "batch_id", "heavy_chain_id", "name", "engine",
            "status", "fasta_text", "sequence_hash", "chains_json",
            "total_length", "use_msa_server", "params_json", "iptm", "ptm",
            "confidence_score", "complex_plddt", "dockq", "pdockq", "pdockq2",
            "runtime_seconds", "error_message", "work_dir", "structure_path",
            "celery_task_id", "created_at", "started_at", "finished_at",
            "parent_job_id", "stage", "results_json",
        ),
    }


def test_auth_imports_keep_dependency_identity() -> None:
    dependencies = importlib.import_module("app.core.dependencies")
    security = importlib.import_module("app.core.security")
    router = importlib.import_module("app.modules.auth.router")

    assert dependencies.decode_token is security.decode_token
    assert router.create_access_token is security.create_access_token
    assert router.hash_password is security.hash_password
    assert router.verify_password is security.verify_password
    assert router.get_current_user is dependencies.get_current_user


def test_celery_configuration_and_task_registry_are_unchanged() -> None:
    import worker.tasks  # noqa: F401

    assert celery_app.main == "boltzfold"
    assert celery_app.conf.broker_url == config.settings.redis_url
    assert celery_app.conf.result_backend == config.settings.redis_url
    assert celery_app.conf.include == ["worker.tasks"]
    assert celery_app.conf.task_default_queue == config.settings.celery_gpu_queue
    assert celery_app.conf.task_routes == {
        "worker.tasks.run_fold_job": {"queue": config.settings.celery_gpu_queue},
        "worker.tasks.run_md_job": {"queue": config.settings.celery_gpu_queue},
    }
    assert {
        name for name in celery_app.tasks if name.startswith("worker.tasks.run_")
    } == TASK_NAMES


def test_router_registry_order_identity_and_main_registration() -> None:
    expected = tuple(importlib.import_module(name).router for name in ROUTER_MODULES)
    assert isinstance(ROUTERS, tuple)
    assert ROUTERS == expected
    assert all(actual is wanted for actual, wanted in zip(ROUTERS, expected, strict=True))

    from app.main import app

    registered = tuple(
        route.original_router
        for route in app.routes
        if hasattr(route, "original_router")
    )
    assert registered == ROUTERS


def test_old_modules_are_removed_and_startup_uses_new_celery_path() -> None:
    old_files = (
        "config.py", "database.py", "models.py", "db_migrate.py",
        "celery_app.py", "auth.py", "deps.py", "engines.py", "queue_service.py",
    )
    assert all(not (ROOT / "app" / name).exists() for name in old_files)
    assert not (ROOT / "app" / "routers").exists()

    start = (ROOT / "scripts" / "start_platform.sh").read_text(encoding="utf-8")
    stop = (ROOT / "scripts" / "stop_platform.sh").read_text(encoding="utf-8")
    assert "-A app.core.celery worker" in start
    assert 'celery -A app.core.celery worker' in stop
