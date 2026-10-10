from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from integrations.boltz2.npu_remote import npu_remote_enabled, remote_job_id, run_boltz_predict_npu


def test_npu_remote_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BOLTZ_NPU_REMOTE", raising=False)
    assert npu_remote_enabled() is False
    monkeypatch.setenv("BOLTZ_NPU_REMOTE", "true")
    assert npu_remote_enabled() is True


def test_run_boltz_predict_npu_builds_submit_command(tmp_path: Path, monkeypatch):
    yaml = tmp_path / "input.yaml"
    yaml.write_text("version: 1\n", encoding="utf-8")
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        (tmp_path / "log.txt").write_text("ok-remote\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "stdout", "")

    monkeypatch.setattr("integrations.boltz2.npu_remote.subprocess.run", fake_run)
    proc = run_boltz_predict_npu(
        yaml,
        tmp_path,
        use_msa_server=True,
        diffusion_samples=5,
        max_parallel_samples=5,
        recycling_steps=3,
    )
    assert proc.returncode == 0
    assert captured["cmd"][0] == "bash"
    assert captured["cmd"][2:6] == ["--job-id", remote_job_id(tmp_path), "--yaml", str(yaml)]
    left = tmp_path / "campaign_a" / "fold" / "WT"
    right = tmp_path / "campaign_b" / "fold" / "WT"
    assert remote_job_id(left) != remote_job_id(right)
    assert remote_job_id(left).endswith("fold__WT")
    assert captured["env"]["DIFFUSION_SAMPLES"] == "5"
    assert captured["env"]["MAX_PARALLEL_SAMPLES"] == "5"
    assert captured["env"]["USE_MSA_SERVER"] == "1"
    assert "ok-remote" in (proc.stdout or "")


def test_dispatch_job_uses_fold_queue_when_npu_remote(monkeypatch):
    from app.modules.fold import service

    seen: dict = {}

    def fake_fold(task, job_id):
        seen["fold"] = job_id
        return SimpleNamespace(id="fold-task")

    def fake_gpu(task, job_id):
        seen["gpu"] = job_id
        return SimpleNamespace(id="gpu-task")

    monkeypatch.setattr(service, "dispatch_to_fold", fake_fold)
    monkeypatch.setattr(service, "dispatch_to_gpu", fake_gpu)
    monkeypatch.setattr(service.settings, "boltz_npu_remote", True)

    job = SimpleNamespace(id="job-b", engine="boltz2", celery_task_id=None)
    service.dispatch_job(None, job)
    assert seen == {"fold": "job-b"}
    assert job.celery_task_id == "fold-task"

    job2 = SimpleNamespace(id="job-e", engine="esmfold2", celery_task_id=None)
    service.dispatch_job(None, job2)
    assert seen == {"fold": "job-b", "gpu": "job-e"}
    assert job2.celery_task_id == "gpu-task"
