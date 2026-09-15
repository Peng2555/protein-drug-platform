"""兼容入口：SASA 实现已迁移到 boltzfold_shared。"""

from boltzfold_shared.geometry.sasa import THREE_TO_ONE, load_atoms, res_iter, residue_sasa

__all__ = ["THREE_TO_ONE", "load_atoms", "res_iter", "residue_sasa"]
