"""抗体编号与折叠共享接口。"""

from boltzfold_shared.antibody.cdr import (
    KABAT_CDR_HEAVY,
    KABAT_CDR_LIGHT,
    annotate_antibody_chain,
    annotate_regions,
    format_kabat_number,
    kabat_labels_for_sequence,
    region_for_index,
)
from boltzfold_shared.antibody.folding import fold_antibody

__all__ = [
    "KABAT_CDR_HEAVY",
    "KABAT_CDR_LIGHT",
    "annotate_antibody_chain",
    "annotate_regions",
    "fold_antibody",
    "format_kabat_number",
    "kabat_labels_for_sequence",
    "region_for_index",
]
