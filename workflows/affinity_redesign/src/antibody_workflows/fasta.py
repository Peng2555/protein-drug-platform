"""兼容入口：实现已迁移到 boltzfold_shared。"""

from boltzfold_shared.io.fasta import parse_fasta, write_fasta

__all__ = ["parse_fasta", "write_fasta"]
