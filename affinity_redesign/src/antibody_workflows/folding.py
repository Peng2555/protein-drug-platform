"""旧折叠入口的 affinity backend 兼容适配。"""

from pathlib import Path


def fold_antibody(fasta: Path, fold_root: Path, job_id: str = "WT") -> Path:
    """保留旧 monkeypatch/import 契约；新工作流不再依赖此适配。"""
    from affinity_redesign.tracks.boltz2 import fold_complex

    data = fold_complex(
        fasta,
        fold_root,
        job_id,
        use_msa_server=True,
        recycling_steps=3,
        sampling_steps=200,
        diffusion_samples=3,
    )
    if data.get("status") != "ok":
        raise RuntimeError(data.get("error") or "Boltz2 折抗体失败")
    prediction = data.get("pred_pdb") or data.get("pred_cif")
    if not prediction or not Path(prediction).is_file():
        raise RuntimeError("Boltz2 未产出 pred.pdb/cif")
    return Path(prediction)

__all__ = ["fold_antibody"]
