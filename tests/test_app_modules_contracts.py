"""业务模块纵向布局、导入与 Router 注册契约。"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

MODULE_FILES = {
    "affinity_redesign": {"__init__.py", "router.py", "service.py", "progress.py"},
    "masking_peptide": {"__init__.py", "router.py", "service.py"},
    "hydro_redesign": {"__init__.py", "router.py", "service.py"},
    "cic_profile": {"__init__.py", "router.py", "service.py"},
    "tnp_profile": {"__init__.py", "router.py", "service.py"},
}

ROUTER_SERVICE_EXPORTS = {
    "affinity_redesign": {
        "create_and_queue_affinity_redesign_job",
        "save_structure_upload",
    },
    "masking_peptide": {
        "create_and_queue_masking_peptide_job",
        "prepare_from_body",
        "save_structure_upload",
    },
    "hydro_redesign": {
        "create_and_queue_hydro_redesign_batch",
        "create_and_queue_hydro_redesign_job",
        "dispatch_hydro_redesign_jobs",
        "parse_vhh_records",
        "save_structure_upload",
    },
    "cic_profile": {
        "create_and_queue_cic_profile_job",
        "save_structure_upload",
    },
    "tnp_profile": {
        "create_and_queue_tnp_profile_batch",
        "create_and_queue_tnp_profile_job",
        "dispatch_tnp_profile_jobs",
        "parse_vhh_records",
        "save_structure_upload",
    },
}

SECOND_MODULE_FILES = {
    "fold": {
        "__init__.py",
        "router.py",
        "batch_router.py",
        "service.py",
        "samples.py",
        "interface.py",
    },
    "md": {"__init__.py", "router.py", "service.py"},
    "design": {"__init__.py", "router.py", "service.py"},
    "developability": {"__init__.py", "router.py", "service.py"},
    "rosetta_eval": {"__init__.py", "router.py", "service.py"},
}

SECOND_ROUTER_SERVICE_EXPORTS = {
    "fold": {"create_and_queue_job", "dispatch_job", "fasta_from_seqs", "sequence_hash"},
    "md": {"create_and_queue_md_job", "resolve_structure_path", "save_uploaded_structure"},
    "design": {"create_and_queue_design_job", "save_uploaded_structure"},
    "developability": {
        "create_and_queue_developability_job",
        "save_uploaded_structure",
    },
    "rosetta_eval": {"_fold_variant", "create_and_queue_rosetta_eval_job", "save_upload"},
}

OPENAPI_SHA256 = "4b78bbdb5ef2436d093e7b860bce0455dcca55519f57c649ae459f82e9055538"


def test_first_module_group_has_exact_vertical_layout():
    app_dir = Path(__file__).parents[1] / "app"
    modules_dir = app_dir / "modules"

    assert (modules_dir / "__init__.py").is_file()
    for name, expected_files in MODULE_FILES.items():
        assert {path.name for path in (modules_dir / name).glob("*.py")} == expected_files

    old_files = {
        *(app_dir / f"{name}_service.py" for name in MODULE_FILES),
        *(app_dir / "routers" / f"{name}_jobs.py" for name in MODULE_FILES),
        app_dir / f"{'affinity_redesign'}_progress.py",
    }
    assert not any(path.exists() for path in old_files)


def test_router_imports_keep_service_object_identity():
    for name, exports in ROUTER_SERVICE_EXPORTS.items():
        router_module = importlib.import_module(f"app.modules.{name}.router")
        service_module = importlib.import_module(f"app.modules.{name}.service")
        assert router_module.__name__ == f"app.modules.{name}.router"
        assert service_module.__name__ == f"app.modules.{name}.service"
        for export in exports:
            assert getattr(router_module, export) is getattr(service_module, export)

    affinity_router = importlib.import_module("app.modules.affinity_redesign.router")
    affinity_progress = importlib.import_module("app.modules.affinity_redesign.progress")
    assert (
        affinity_router.collect_affinity_redesign_progress
        is affinity_progress.collect_affinity_redesign_progress
    )


def test_main_registers_new_router_modules_in_original_order():
    import app.main as main

    names = tuple(MODULE_FILES)
    modules = [importlib.import_module(f"app.modules.{name}.router") for name in names]
    assert [getattr(main, name) for name in names] == modules

    registered_routers = [
        route.original_router
        for route in main.app.routes
        if hasattr(route, "original_router")
    ]
    positions = [registered_routers.index(module.router) for module in modules]
    assert positions == sorted(positions)


def test_second_module_group_has_exact_vertical_layout_and_no_old_files():
    app_dir = Path(__file__).parents[1] / "app"
    modules_dir = app_dir / "modules"
    for name, expected_files in SECOND_MODULE_FILES.items():
        assert {path.name for path in (modules_dir / name).glob("*.py")} == expected_files

    old_files = {
        app_dir / "job_service.py",
        app_dir / "fold_samples.py",
        app_dir / "interface_service.py",
        app_dir / "md_service.py",
        app_dir / "design_service.py",
        app_dir / "developability_service.py",
        app_dir / "rosetta_eval_service.py",
        *(app_dir / "routers" / name for name in (
            "jobs.py",
            "batches.py",
            "md_jobs.py",
            "design_jobs.py",
            "developability_jobs.py",
            "rosetta_eval_jobs.py",
        )),
    }
    assert not any(path.exists() for path in old_files)


def test_second_module_group_has_zero_old_import_references():
    root = Path(__file__).parents[1]
    old_modules = (
        *(f"app.{name}_service" for name in (
            "job",
            "interface",
            "md",
            "design",
            "developability",
            "rosetta_eval",
        )),
        "app." + "fold_samples",
        *(f"app.routers.{name}" for name in (
            "jobs",
            "batches",
            "md_jobs",
            "design_jobs",
            "developability_jobs",
            "rosetta_eval_jobs",
        )),
    )
    sources = [
        path.read_text(encoding="utf-8")
        for directory in ("app", "worker", "tests")
        for path in (root / directory).rglob("*.py")
    ]
    assert all(old_module not in source for old_module in old_modules for source in sources)


def test_second_router_imports_keep_service_object_identity():
    for name, exports in SECOND_ROUTER_SERVICE_EXPORTS.items():
        router_module = importlib.import_module(f"app.modules.{name}.router")
        service_module = importlib.import_module(f"app.modules.{name}.service")
        for export in exports:
            assert getattr(router_module, export) is getattr(service_module, export)

    batch_router = importlib.import_module("app.modules.fold.batch_router")
    fold_service = importlib.import_module("app.modules.fold.service")
    for export in ("create_and_queue_job", "dispatch_job", "sequence_hash"):
        assert getattr(batch_router, export) is getattr(fold_service, export)


def test_main_registers_second_group_in_original_order():
    import app.main as main

    modules = [
        importlib.import_module("app.modules.fold.router"),
        importlib.import_module("app.modules.fold.batch_router"),
        importlib.import_module("app.modules.md.router"),
        importlib.import_module("app.modules.developability.router"),
        importlib.import_module("app.modules.design.router"),
        importlib.import_module("app.modules.rosetta_eval.router"),
    ]
    assert [
        main.fold,
        main.fold_batches,
        main.md,
        main.developability,
        main.design,
        main.rosetta_eval,
    ] == modules

    registered_routers = [
        route.original_router
        for route in main.app.routes
        if hasattr(route, "original_router")
    ]
    positions = [registered_routers.index(module.router) for module in modules]
    assert positions == sorted(positions)


def test_openapi_contract_is_stable_after_second_module_move():
    from app.main import app

    schema = app.openapi()
    payload = json.dumps(
        schema,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert len(schema["paths"]) == 97
    assert hashlib.sha256(payload.encode()).hexdigest() == OPENAPI_SHA256
