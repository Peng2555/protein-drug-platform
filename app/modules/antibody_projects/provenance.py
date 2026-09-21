"""序列快照与溯源校验的基础规则。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping


VALID_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWYX")
_DNA_LETTERS = frozenset("ACGTN")
_CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def _letters_only(sequence: str) -> str:
    return re.sub(r"[^A-Za-z]", "", sequence or "").upper()


def is_nucleic_acid(sequence: str) -> bool:
    compact = _letters_only(sequence).replace("U", "T")
    return len(compact) >= 60 and set(compact) <= _DNA_LETTERS


def translate_cds(sequence: str) -> str:
    """标准遗传密码翻译 CDS；末尾终止密码子丢弃，内部终止则报错。"""
    cds = _letters_only(sequence).replace("U", "T")
    if not cds:
        raise ValueError("核酸序列不能为空")
    if "N" in cds:
        raise ValueError("核酸含有简并碱基 N，无法唯一翻译")
    if len(cds) % 3:
        raise ValueError(f"核酸长度 {len(cds)} 不是 3 的倍数，请提供完整 CDS")
    residues: list[str] = []
    for index in range(0, len(cds), 3):
        codon = cds[index : index + 3]
        amino = _CODON_TABLE.get(codon)
        if amino is None:
            raise ValueError(f"无法翻译密码子 {codon}")
        if amino == "*":
            if index + 3 == len(cds):
                break
            raise ValueError(f"核酸在第 {index // 3 + 1} 个密码子提前终止")
        residues.append(amino)
    if not residues:
        raise ValueError("翻译结果为空")
    return "".join(residues)


def _validate_amino_acids(sequence: str) -> str:
    compact = re.sub(r"\s+", "", sequence or "").upper()
    if not compact:
        raise ValueError("序列不能为空")
    invalid = sorted(set(compact) - VALID_AMINO_ACIDS)
    if invalid:
        raise ValueError(f"序列包含非法氨基酸字符: {''.join(invalid)}")
    return compact


def protein_and_optional_cds(sequence: str) -> tuple[str, str | None]:
    """氨基酸原样校验；纯核酸则翻译，并返回原始 CDS。"""
    letters = _letters_only(sequence)
    if is_nucleic_acid(letters):
        protein = translate_cds(letters)
        return _validate_amino_acids(protein), letters.replace("U", "T")
    return _validate_amino_acids(strip_appended_dna(sequence)), None


def strip_appended_dna(sequence: str) -> str:
    """去掉氨基酸后面整段拷贝的 DNA；纯 DNA 交给翻译，不在这里处理。"""
    compact = re.sub(r"\s+", "", sequence or "").upper()
    if not compact:
        return compact
    if set(compact) <= _DNA_LETTERS:
        raise ValueError("这是 DNA 序列，请提供氨基酸序列或完整 CDS")
    if len(compact) >= 200 and len(compact) % 4 == 0:
        n = len(compact) // 4
        protein, cds = compact[:n], compact[n:]
        if set(cds) <= _DNA_LETTERS and (set(protein) - _DNA_LETTERS):
            return protein
    return compact


def normalize_sequence(sequence: str) -> str:
    """统一为氨基酸大写序列；核酸会先按标准密码子翻译。"""
    protein, _cds = protein_and_optional_cds(sequence)
    return protein


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(normalize_sequence(sequence).encode("ascii")).hexdigest()


def version_sha256(chains: Mapping[str, str]) -> str:
    """按链角色排序生成稳定版本指纹，避免字典顺序影响结果。"""
    if not chains:
        raise ValueError("版本至少需要一条链序列")
    canonical = "\n".join(
        f"{role.upper()}:{normalize_sequence(sequence)}"
        for role, sequence in sorted(chains.items(), key=lambda item: item[0].upper())
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def diff_sequences(base: str, target: str) -> list[dict]:
    """用简单全局比对返回替换、插入和删除；位置按目标序列的一基编号。"""
    left = normalize_sequence(base)
    right = normalize_sequence(target)
    rows, cols = len(left) + 1, len(right) + 1
    scores = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        scores[i][0] = i
    for j in range(cols):
        scores[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            scores[i][j] = min(
                scores[i - 1][j - 1] + (left[i - 1] != right[j - 1]),
                scores[i - 1][j] + 1,
                scores[i][j - 1] + 1,
            )

    changes: list[dict] = []
    i, j = len(left), len(right)
    while i or j:
        if i and j:
            diagonal = scores[i - 1][j - 1] + (left[i - 1] != right[j - 1])
            if scores[i][j] == diagonal:
                if left[i - 1] != right[j - 1]:
                    changes.append(
                        {
                            "mutation_type": "substitution",
                            "sequence_position": j,
                            "from_aa": left[i - 1],
                            "to_aa": right[j - 1],
                        }
                    )
                i -= 1
                j -= 1
                continue
        if i and scores[i][j] == scores[i - 1][j] + 1:
            changes.append(
                {
                    "mutation_type": "deletion",
                    "sequence_position": j + 1,
                    "from_aa": left[i - 1],
                    "to_aa": None,
                }
            )
            i -= 1
            continue
        changes.append(
            {
                "mutation_type": "insertion",
                "sequence_position": j,
                "from_aa": None,
                "to_aa": right[j - 1],
            }
        )
        j -= 1

    changes.reverse()
    return changes
