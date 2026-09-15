"""Rosetta worker 状态落库的回归测试。"""

from __future__ import annotations

from types import SimpleNamespace


def test_rosetta_worker_success_commits_done_and_returns(monkeypatch, tmp_path):
    from worker import tasks

    job = SimpleNamespace(
        id="rosetta-job-1",
        engine="rosetta_interface_eval",
        status="queued",
        stage="queued",
        params_json={"variants": [{"name": "WT", "path": "/not/read/by-mock.pdb"}]},
        work_dir=str(tmp_path / "rosetta-work"),
        started_at=None,
        finished_at=None,
        runtime_seconds=None,
        results_json=None,
        error_message="old error",
        celery_task_id=None,
    )

    class FakeSession:
        def __init__(self):
            self.commit_count = 0
            self.closed = False

        def get(self, _model, job_id):
            return job if job_id == job.id else None

        def commit(self):
            self.commit_count += 1

        def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    def fake_runner(*, work_dir, params, on_stage):
        assert work_dir == tmp_path / "rosetta-work"
        assert params == job.params_json
        on_stage("scoring")
        return SimpleNamespace(
            status="ok",
            stage="done",
            seconds=1.25,
            results={"best_variant": "WT"},
            error=None,
        )

    monkeypatch.setattr(tasks, "run_rosetta_eval_pipeline", fake_runner)

    result = tasks.run_rosetta_eval_job.run(job.id)

    assert result == {"job_id": job.id, "status": "done"}
    assert job.status == "done"
    assert job.stage == "done"
    assert job.runtime_seconds == 1.25
    assert job.results_json == {"best_variant": "WT"}
    assert job.error_message is None
    # running、阶段回调和最终 done 都应各自提交。
    assert session.commit_count >= 3
    assert session.closed is True
