"""兼容入口：实现已迁移到 boltzfold_shared。"""

from boltzfold_shared.io.structures import copy_structure_input, export_structure_files, to_cif

__all__ = ["copy_structure_input", "export_structure_files", "to_cif"]
