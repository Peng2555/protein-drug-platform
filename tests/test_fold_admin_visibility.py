"""管理员可以查看他人的结构预测，普通用户仍然只能看自己的。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user, get_db
from app.core.models import Batch, Job, User
from app.modules.fold.batch_router import router as batch_router
from app.modules.fold.router import router as job_router


def _user(db, username: str, *, admin: bool) -> User:
    user = User(
        username=username,
        email=f"{username}@example.test",
        password_hash="not-used",
        is_active=True,
        is_admin=admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    return user


def _job(db, user_id: str, name: str, engine: str) -> Job:
    job = Job(
        user_id=user_id,
        name=name,
        engine=engine,
        fasta_text=">A\nAAAAA\n",
        sequence_hash=name,
        chains_json={"A": 5},
        total_length=5,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    db.expunge(job)
    return job


def _batch(db, user_id: str, name: str) -> Batch:
    batch = Batch(
        user_id=user_id,
        name=name,
        batch_type="vhh_panel",
        target_name="target",
        target_sequence="AAAAA",
        heavy_chain_count=1,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    db.expunge(batch)
    return batch


def test_admin_sees_other_users_fold_jobs_but_cannot_change_them(sqlite_sessions) -> None:
    with sqlite_sessions() as db:
        owner = _user(db, "owner", admin=False)
        admin = _user(db, "admin", admin=True)
        outsider = _user(db, "outsider", admin=False)
        fold_job = _job(db, owner.id, "owner-fold", "boltz2")
        other_engine = _job(db, owner.id, "owner-design", "protein_mpnn")
        batch = _batch(db, owner.id, "owner-batch")

    current = {"value": outsider}
    app = FastAPI()
    app.include_router(job_router)
    app.include_router(batch_router)

    def isolated_db():
        with sqlite_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    app.dependency_overrides[get_current_user] = lambda: current["value"]

    with TestClient(app) as client:
        current["value"] = outsider
        hidden = client.get("/api/jobs")
        assert hidden.status_code == 200
        assert hidden.json()["items"] == []
        assert client.get(f"/api/jobs/{fold_job.id}").status_code == 404
        assert client.get("/api/batches").json()["items"] == []

        current["value"] = owner
        own = client.get("/api/jobs")
        assert [item["name"] for item in own.json()["items"]] == ["owner-fold"]
        assert own.json()["items"][0]["owner_username"] == "owner"

        current["value"] = admin
        visible = client.get("/api/jobs")
        assert visible.status_code == 200
        assert [item["name"] for item in visible.json()["items"]] == ["owner-fold"]
        assert visible.json()["items"][0]["owner_username"] == "owner"
        detail = client.get(f"/api/jobs/{fold_job.id}")
        assert detail.status_code == 200
        assert detail.json()["owner_username"] == "owner"
        assert client.get(f"/api/jobs/{other_engine.id}").status_code == 404
        denied = client.delete(f"/api/jobs/{fold_job.id}")
        assert denied.status_code == 403

        batches = client.get("/api/batches")
        assert batches.status_code == 200
        assert batches.json()["items"][0]["name"] == "owner-batch"
        assert batches.json()["items"][0]["owner_username"] == "owner"
        assert client.get(f"/api/batches/{batch.id}").status_code == 200
        assert client.delete(f"/api/batches/{batch.id}").status_code == 403
