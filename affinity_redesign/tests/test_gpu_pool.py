from affinity_redesign.tracks.gpu_pool import select_idle_gpu_ids


def test_select_idle_includes_assigned_and_skips_busy(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("CELERY_GPU_COUNT", "4")

    def fake_smi():
        return [
            {"index": 0, "mem_used_mib": 12000.0, "util": 80.0},
            {"index": 1, "mem_used_mib": 200.0, "util": 0.0},
            {"index": 2, "mem_used_mib": 18000.0, "util": 90.0},
            {"index": 3, "mem_used_mib": 300.0, "util": 1.0},
        ]

    monkeypatch.setattr("affinity_redesign.tracks.gpu_pool._query_nvidia_smi", fake_smi)
    assert select_idle_gpu_ids() == [0, 1, 3]


def test_select_idle_caps_at_max(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setenv("CELERY_GPU_COUNT", "8")

    def fake_smi():
        return [
            {"index": i, "mem_used_mib": 100.0, "util": 0.0} for i in range(4)
        ]

    monkeypatch.setattr("affinity_redesign.tracks.gpu_pool._query_nvidia_smi", fake_smi)
    assert select_idle_gpu_ids(max_gpus=2) == [0, 1]
