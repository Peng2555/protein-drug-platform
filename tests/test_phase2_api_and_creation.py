"""第二阶段 API smoke 与创建/派发契约测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.models import Batch, Job


def test_health_is_safe_and_protected_api_requires_auth(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_sessions,
):
    import app.main as main
    from app.core.database import get_db

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement):
            return None

    class FakeRedis:
        def ping(self):
            return True

        def llen(self, _queue):
            return 0

    monkeypatch.setattr(main.engine, "connect", lambda: FakeConnection())
    monkeypatch.setattr(main, "SessionLocal", sqlite_sessions)
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(from_url=lambda _url: FakeRedis()),
    )

    def isolated_db():
        with sqlite_sessions() as db:
            yield db

    main.app.dependency_overrides[get_db] = isolated_db
    client = TestClient(main.app)
    try:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "database": "ok",
            "redis": "ok",
            "queue_depth": 0,
            "running_jobs": 0,
            "gpu_workers": main.settings.celery_gpu_count,
        }

        response = client.get("/api/jobs")
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

        response = client.get("/api/route-that-does-not-exist")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
    finally:
        main.app.dependency_overrides.clear()
        client.close()


@pytest.mark.parametrize(
    "path",
    [
        "/home",
        "/login",
        "/fold/new",
        "/fold/batches/batch-1",
        "/hydro-redesign/new",
        "/hydro-redesign/batch/batch-2",
        "/tnp-profile/batch/batch-3",
    ],
)
def test_spa_routes_fall_back_to_packaged_index(tmp_path: Path, path: str):
    from app.main import SPAStaticFiles

    dist = tmp_path / "dist"
    dist.mkdir()
    marker = "<html><body>isolated-spa-index</body></html>"
    (dist / "index.html").write_text(marker, encoding="utf-8")

    test_app = FastAPI()
    test_app.mount("/", SPAStaticFiles(directory=str(dist), html=True), name="test-spa")
    response = TestClient(test_app).get(path)

    assert response.status_code == 200
    assert response.text == marker


def test_regular_job_router_commits_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    sqlite_sessions,
    active_user,
):
    from app.modules.fold import router as jobs_router
    from app.schemas import JobCreate

    dispatched: list[str] = []

    def assert_committed_then_dispatch(db, job):
        with sqlite_sessions() as independent_db:
            visible = independent_db.get(Job, job.id)
            assert visible is not None
            assert visible.status == "queued"
            assert visible.name == "commit-before-dispatch"
        dispatched.append(job.id)
        job.celery_task_id = "fake-celery-task"

    monkeypatch.setattr(jobs_router, "dispatch_job", assert_committed_then_dispatch)
    with sqlite_sessions() as db:
        output = jobs_router.create_job(
            JobCreate(
                name="commit-before-dispatch",
                fasta=">A\nACDEFGHIK\n",
                engine="boltz2",
                use_msa_server=False,
            ),
            db=db,
            user=active_user,
        )

    assert dispatched == [output.id]
    with sqlite_sessions() as db:
        stored = db.get(Job, output.id)
        assert stored is not None
        assert stored.user_id == active_user.id
        assert stored.engine == "boltz2"
        assert stored.chains_json == {"A": 9}
        assert stored.total_length == 9
        assert stored.celery_task_id == "fake-celery-task"


def test_hydro_and_tnp_batches_defer_until_explicit_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sqlite_sessions,
    active_user,
):
    from app.modules.hydro_redesign import service as hydro
    from app.modules.tnp_profile import service as tnp

    monkeypatch.setattr(hydro.settings, "hydro_redesign_out_root", tmp_path / "hydro")
    monkeypatch.setattr(tnp.settings, "tnp_profile_out_root", tmp_path / "tnp")
    dispatched: list[tuple[str, str]] = []

    def fake_hydro_dispatch(_task, job_id):
        dispatched.append(("hydro", job_id))
        return SimpleNamespace(id=f"hydro-task-{job_id}")

    def fake_tnp_dispatch(_task, job_id):
        dispatched.append(("tnp", job_id))
        return SimpleNamespace(id=f"tnp-task-{job_id}")

    monkeypatch.setattr(hydro, "dispatch_to_gpu", fake_hydro_dispatch)
    monkeypatch.setattr(tnp, "dispatch_to_gpu", fake_tnp_dispatch)
    sequence = "Q" * 80
    fasta = f">vhh-a\n{sequence}\n>vhh-b\n{sequence}\n"

    with sqlite_sessions() as db:
        hydro_batch, hydro_jobs = hydro.create_and_queue_hydro_redesign_batch(
            db,
            user_id=active_user.id,
            name="hydro-batch",
            fasta_text=fasta,
            allow_cdr=True,
            allow_charged=False,
        )
        tnp_batch, tnp_jobs = tnp.create_and_queue_tnp_profile_batch(
            db,
            user_id=active_user.id,
            name="tnp-batch",
            fasta_text=fasta,
        )

        assert dispatched == []
        db.commit()

        hydro.dispatch_hydro_redesign_jobs(hydro_jobs)
        tnp.dispatch_tnp_profile_jobs(tnp_jobs)
        db.commit()

        hydro_batch_id = hydro_batch.id
        tnp_batch_id = tnp_batch.id
        hydro_job_ids = [job.id for job in hydro_jobs]
        tnp_job_ids = [job.id for job in tnp_jobs]

    assert [kind for kind, _ in dispatched] == ["hydro", "hydro", "tnp", "tnp"]
    with sqlite_sessions() as db:
        stored_hydro = db.get(Batch, hydro_batch_id)
        stored_tnp = db.get(Batch, tnp_batch_id)
        assert stored_hydro is not None
        assert stored_hydro.batch_type == "hydro_redesign"
        assert stored_hydro.heavy_chain_count == 2
        assert stored_tnp is not None
        assert stored_tnp.batch_type == "tnp_profile"
        assert stored_tnp.heavy_chain_count == 2

        for expected_engine, expected_batch_id, job_ids in (
            ("hydro_redesign", hydro_batch_id, hydro_job_ids),
            ("tnp_profile", tnp_batch_id, tnp_job_ids),
        ):
            jobs = [db.get(Job, job_id) for job_id in job_ids]
            assert all(job is not None for job in jobs)
            assert {job.engine for job in jobs} == {expected_engine}
            assert {job.heavy_chain_id for job in jobs} == {"vhh-a", "vhh-b"}
            assert {job.batch_id for job in jobs} == {expected_batch_id}
            assert all(job.celery_task_id for job in jobs)
