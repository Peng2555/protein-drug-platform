"""首批业务模块纵向布局、导入与 Router 注册契约。"""

from __future__ import annotations

import importlib
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
