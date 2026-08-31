"""Campaign 与突变记录的 Pydantic 模型。"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class AntibodyFormat(str, Enum):
    vhh = "vhh"
    igg = "igg"


class ChainConfig(BaseModel):
    heavy: str = "H"
    light: str | None = None
    antigen: str = "A"


class StructureConfig(BaseModel):
    source: Literal["pdb", "boltz2", "esmfold2", "fold_job"] = "pdb"
    path: str | None = "input/complex.pdb"
    multichain: bool = True
    fold_job_id: str | None = None


class PlmTrackConfig(BaseModel):
    models: list[str] = Field(default_factory=lambda: ["esm1b", "esm1v_ensemble"])
    esm2_explore: bool = False
    consensus_k: int = 3
    top_per_chain: int = 0  # 0 = 保留全部共识通过
    maxrep: int = 0  # 0 = 不限制同位点条数
    scan_regions: list[str] = Field(default_factory=lambda: ["FR", "CDR"])


class StructureTrackConfig(BaseModel):
    engine: Literal["antifold", "esm_if1"] = "antifold"
    dll_threshold: float = 0.0  # 结构轨过门：dll > 此值才进入 merge
    top_per_chain: int = 0  # 0 = 保留全部过门（不做 top-N 截断）
    maxrep: int = 0  # 0 = 不限制同位点条数
    scan_regions: list[str] = Field(default_factory=lambda: ["FR", "CDR"])


class MergeConfig(BaseModel):
    # A=两轨交集 / B=仅结构 / C=仅 PLM
    # 不做「每轨 top-N」；B 默认软上限，避免结构轨过门过多撑爆 Boltz2
    tier_quotas: dict[str, int | str] = Field(
        default_factory=lambda: {"A": "all", "B": 100, "C": "all"}
    )


class FilterConfig(BaseModel):
    freeze_cysteine: bool = True
    block_new_nglyc: bool = True
    # N 端冻住前 4（QVQL）；C 端只冻 TVSS，不整段冻 FR4
    freeze_nterm: int = 4
    freeze_cterm: int = 4
    freeze_fr4: bool = False


class RescoreConfig(BaseModel):
    """Boltz2 相对筛选 + Rosetta 界面能。不含 AF3Score。"""

    delta_iptm_min: float = -0.03  # ΔipTM 低于此值视为变差
    max_ddg: float = 3.0  # Rosetta ddG 高于此值不进湿实验短名单
    nstruct: int = 1
    n_jobs: int = 0  # 0 = 自动：尽量用满 CPU（核数减少量预留）
    use_msa_server: bool = True
    recycling_steps: int = 3
    sampling_steps: int = 200
    diffusion_samples: int = 1
    # 0 = 不限制；>0 时按 A→B→C 优先级截断进入 Boltz2 的总数（round1 全表仍保留）
    max_variants: int = 0
    # 0 = 自动：空闲几张卡用几张（上限 CELERY_GPU_COUNT）；>0 时最多用这么多张
    n_gpus: int = 0


class Round1Config(BaseModel):
    antibody_format: AntibodyFormat = AntibodyFormat.vhh
    chains: ChainConfig = Field(default_factory=ChainConfig)
    structure: StructureConfig = Field(default_factory=StructureConfig)
    plm: PlmTrackConfig = Field(default_factory=PlmTrackConfig)
    structure_track: StructureTrackConfig = Field(default_factory=StructureTrackConfig)
    merge: MergeConfig = Field(default_factory=MergeConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    rescore: RescoreConfig = Field(default_factory=RescoreConfig)


class WetlabConfig(BaseModel):
    round1_metric: Literal["ic50", "kd"] = "ic50"
    beneficial_threshold: float = 1.1


class CampaignConfig(BaseModel):
    name: str
    slug: str
    notes: str = ""
    antibody_format: AntibodyFormat = AntibodyFormat.vhh
    chains: ChainConfig = Field(default_factory=ChainConfig)
    structure: StructureConfig = Field(default_factory=StructureConfig)
    round1_config: str | None = None
    round2_config: str | None = None
    wetlab: WetlabConfig = Field(default_factory=WetlabConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> CampaignConfig:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(data)


class MutationRecord(BaseModel):
    chain: str
    position: int
    wt: str
    mut: str
    region: str = ""
    tier: Literal["A", "B", "C"] | None = None
    plm_score: float | None = None
    structure_score: float | None = None
    label: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.label:
            self.label = f"{self.wt}{self.position}{self.mut}"


def load_round1_config(path: Path) -> Round1Config:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Round1Config.model_validate(data)
