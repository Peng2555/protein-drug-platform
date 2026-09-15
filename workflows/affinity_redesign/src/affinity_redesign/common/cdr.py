"""兼容入口：CDR 实现已迁移到 boltzfold_shared。"""

from boltzfold_shared.antibody.cdr import (
    KABAT_CDR_HEAVY,
    KABAT_CDR_LIGHT,
    annotate_antibody_chain,
    annotate_regions,
    region_for_index,
)

__all__ = [
    "KABAT_CDR_HEAVY",
    "KABAT_CDR_LIGHT",
    "annotate_antibody_chain",
    "annotate_regions",
    "region_for_index",
]
