"""Structure prediction schemas."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChainInput(BaseModel):
    id: str
    sequence: str


class EsmFold2Params(BaseModel):
    num_loops: int = Field(default=10, ge=1, le=30)
    num_sampling_steps: int = Field(default=68, ge=1, le=200)
    num_diffusion_samples: int = Field(default=5, ge=1, le=25)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)


class Boltz2Params(BaseModel):
    """Boltz2 predict CLI 参数（与本机 boltz predict 对齐）。"""

    recycling_steps: int = Field(default=3, ge=1, le=20)
    sampling_steps: int = Field(default=200, ge=20, le=1000)
    diffusion_samples: int = Field(default=1, ge=1, le=25)
    max_parallel_samples: int | None = Field(default=5, ge=1, le=25)
    step_scale: float | None = Field(default=None, ge=0.5, le=5.0)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    output_format: Literal["mmcif", "pdb"] = "mmcif"
    model: Literal["boltz2", "boltz1"] = "boltz2"
    method: str | None = Field(default=None, max_length=64)
    use_potentials: bool = False
    use_msa_server: bool = True
    msa_pairing_strategy: Literal["greedy", "complete"] = "greedy"
    max_msa_seqs: int = Field(default=8192, ge=64, le=16384)
    subsample_msa: bool = False
    num_subsampled_msa: int = Field(default=1024, ge=16, le=8192)
    write_full_pae: bool = False
    write_full_pde: bool = False
    write_embeddings: bool = False


class BoltzModification(BaseModel):
    position: int = Field(ge=1, le=10000)
    ccd: str = Field(min_length=1, max_length=16)


class BoltzComponent(BaseModel):
    """一条唯一实体；copies>1 时展开为多个链 ID（与 Tamarind / Boltz YAML 一致）。"""

    entity: Literal["protein", "dna", "rna", "ligand"] = "protein"
    ids: list[str] = Field(min_length=1)
    sequence: str | None = None
    smiles: str | None = None
    ccd: str | None = None
    cyclic: bool = False
    modifications: list[BoltzModification] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_entity_fields(self):
        ids = [i.strip() for i in self.ids if i and i.strip()]
        if not ids:
            raise ValueError("每条链至少需要一个 ID")
        if len(ids) != len(set(ids)):
            raise ValueError(f"链 ID 重复: {ids}")
        for cid in ids:
            if len(cid) > 4:
                raise ValueError(f"链 ID「{cid}」超过 4 个字符")
        object.__setattr__(self, "ids", ids)

        if self.entity == "ligand":
            has_smi = bool(self.smiles and self.smiles.strip())
            has_ccd = bool(self.ccd and self.ccd.strip())
            if has_smi == has_ccd:
                raise ValueError("配体需且仅需提供 SMILES 或 CCD 之一")
        else:
            seq = (self.sequence or "").replace(" ", "").replace("\n", "").upper()
            if len(seq) < 2:
                raise ValueError(f"{self.entity} 序列过短")
            object.__setattr__(self, "sequence", seq)
        return self


class BoltzPocketConstraint(BaseModel):
    type: Literal["pocket"] = "pocket"
    binder: str = Field(min_length=1, max_length=4)
    contacts: list[tuple[str, int]] = Field(min_length=1)
    max_distance: float = Field(default=6.0, ge=4.0, le=20.0)
    force: bool = False


class BoltzContactConstraint(BaseModel):
    type: Literal["contact"] = "contact"
    token1: tuple[str, int]
    token2: tuple[str, int]
    max_distance: float = Field(default=6.0, ge=4.0, le=20.0)
    force: bool = False


class BoltzAffinity(BaseModel):
    """仅支持小分子配体相对蛋白靶点的亲和力头（非蛋白–蛋白）。"""

    binder: str = Field(min_length=1, max_length=4)


class JobCreate(BaseModel):
    fasta: str | None = None
    chains: list[ChainInput] | None = None
    name: str | None = Field(default=None, max_length=128)
    engine: Literal["boltz2", "esmfold2"] = "boltz2"
    use_msa_server: bool = True
    boltz_params: Boltz2Params | None = None
    esmfold_params: EsmFold2Params | None = None
    # Boltz 结构化输入（优先于纯 FASTA）
    components: list[BoltzComponent] | None = None
    constraints: list[BoltzPocketConstraint | BoltzContactConstraint] | None = None
    affinity: BoltzAffinity | None = None

    @model_validator(mode="after")
    def _check_input(self):
        has_comp = bool(self.components)
        has_fasta = bool(self.fasta and self.fasta.strip()) or bool(self.chains)
        if self.engine == "boltz2":
            if not has_comp and not has_fasta:
                raise ValueError("请提供 components 或 fasta")
            if self.affinity and has_comp:
                binder = self.affinity.binder
                ligand_ids = {
                    cid
                    for c in self.components or []
                    if c.entity == "ligand"
                    for cid in c.ids
                }
                if binder not in ligand_ids:
                    raise ValueError(
                        f"亲和力 binder「{binder}」必须是小分子配体链 ID；"
                        "Boltz-2 亲和力模块仅支持小分子–蛋白，不支持蛋白–蛋白。"
                    )
                for c in self.components or []:
                    if binder in c.ids and len(c.ids) > 1:
                        raise ValueError("亲和力配体不能有多个 copies")
        else:
            if not has_fasta and not has_comp:
                raise ValueError("请提供序列输入")
        return self
