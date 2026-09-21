"""抗体改造项目的核心业务操作。"""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.cdr_annotation import annotate_antibody_chain
from app.common.csv_decode import read_xlsx_matrix
from app.core.models import Job, User
from app.modules.antibody_projects.access import add_audit, model_snapshot
from app.modules.antibody_projects.models import (
    AntibodyCandidate,
    AntibodyProject,
    AntibodyVersion,
    AntibodyVersionChain,
    ExperimentMeasurement,
    ExperimentRecord,
    ProjectJobLink,
    ProjectMember,
    ProjectRole,
    ProjectStatus,
    SampleBatch,
    VersionMutation,
    VersionStatus,
)
from app.modules.antibody_projects.provenance import (
    diff_sequences,
    normalize_sequence,
    protein_and_optional_cds,
    sequence_sha256,
    version_sha256,
)
from app.schemas.antibody_project import (
    AffinityImportItem,
    AffinityImportRequest,
    AffinityPreviewOut,
    AffinityPreviewRow,
    CandidateCreate,
    ExperimentCreate,
    JobLinkCreate,
    MeasurementInput,
    ProjectCreate,
    ProjectUpdate,
    SampleBatchCreate,
    VersionChainInput,
    VersionCreate,
    VersionImportItem,
    VersionImportRequest,
    VersionOut,
    VersionUpdate,
)


PROJECT_STATUSES = {item.value for item in ProjectStatus}
EDITABLE_PARENT_STATUSES = {
    VersionStatus.locked.value,
    VersionStatus.tested.value,
    VersionStatus.rejected.value,
}
_VERSION_ROUND = re.compile(r"^M(\d+)(?:-(\d+))?$", re.IGNORECASE)
_FASTA_ROLE = re.compile(
    r"^(?P<base>.+?)(?:[_/|. \t-]|chain)+(?P<role>VHH|VH|VL|HEAVY|LIGHT|H|L)$",
    re.IGNORECASE,
)
_FASTA_ROLE_TOKEN = {
    "VHH": "VHH",
    "VH": "VH",
    "HEAVY": "VH",
    "H": "VH",
    "VL": "VL",
    "LIGHT": "VL",
    "L": "VL",
}
_MAX_FASTA_BYTES = 2 * 1024 * 1024
_MAX_TABLE_BYTES = 8 * 1024 * 1024
_NAME_HEADERS = {"蛋白名称", "proteinname", "protein", "抗体名称"}
_SEQ_HEADERS = {
    "基因序列",
    "核酸序列",
    "核苷酸序列",
    "genesequence",
    "dnasequence",
    "cds",
    "dna",
}
_GENE_HEADERS = {"基因名称", "genename", "gene"}
_VH_HEADERS = {"vh基因序列", "vh序列", "重链序列", "heavychain"}
_VL_HEADERS = {"vl基因序列", "vl序列", "轻链序列", "lightchain"}
_AFFINITY_SHEET = "亲和力"
_LOADING_ID_HEADERS = {"loadingsampleid", "上样样品id", "上样id", "上样样品"}
_ANTIGEN_HEADERS = {"sampleid", "抗原", "antigen"}
_LOADING_RESP_HEADERS = {"loadingresponse", "上样响应"}
_RESP_HEADERS = {"response", "结合响应"}
_KD_HEADERS = {"kd", "kd(m)", "kd（m）", "亲和力kd"}
_KA_HEADERS = {"ka", "ka(1/ms)", "ka（1/ms）"}
_KDIS_HEADERS = {"kdis", "kdis(1/s)", "koff", "kd(1/s)"}
_RESULT_HEADERS = {"result", "结果", "判定"}
_CONTROL_RE = re.compile(r"higg|ustekinumab|isotype|对照", re.I)
_BLANK_NUMBER = {"", "-", "–", "—", "/", "na", "n/a", "nan", "无"}
_LIMIT_PREFIX = {
    "<": "<",
    "<=": "<=",
    "≤": "<=",
    "＜": "<",
    ">": ">",
    ">=": ">=",
    "≥": ">=",
    "＞": ">",
}


def _round_of(version: AntibodyVersion) -> int:
    if version.version_code.upper() == "WT" or version.version_number == 0:
        return 0
    matched = _VERSION_ROUND.match(version.version_code)
    if matched:
        return int(matched.group(1))
    return max(version.version_number, 0)


def _next_clone_index(db: Session, candidate_id: str, round_number: int) -> int:
    codes = db.scalars(
        select(AntibodyVersion.version_code).where(
            AntibodyVersion.candidate_id == candidate_id
        )
    ).all()
    prefix = f"M{round_number}-"
    highest = 0
    for code in codes:
        if code.startswith(prefix) and code[len(prefix) :].isdigit():
            highest = max(highest, int(code[len(prefix) :]))
    return highest + 1


def _allocate_engineered_code(
    db: Session, candidate_id: str, parent: AntibodyVersion
) -> tuple[str, int]:
    round_number = _round_of(parent) + 1
    clone = _next_clone_index(db, candidate_id, round_number)
    if clone > 999:
        raise HTTPException(400, "本轮改造已超过 999 条，请从选定版本开始下一轮")
    version_number = round_number * 1000 + clone
    conflict = db.scalar(
        select(AntibodyVersion.id).where(
            AntibodyVersion.candidate_id == candidate_id,
            AntibodyVersion.version_number == version_number,
        )
    )
    if conflict:
        raise HTTPException(409, f"版本序号冲突: {version_number}")
    return f"M{round_number}-{clone:03d}", version_number


def create_project(db: Session, body: ProjectCreate, user: User) -> AntibodyProject:
    code = body.project_code.strip()
    exists = db.scalar(
        select(AntibodyProject.id).where(
            AntibodyProject.owner_id == user.id,
            AntibodyProject.project_code == code,
        )
    )
    if exists:
        raise HTTPException(409, "你已经使用了这个项目编号")

    project = AntibodyProject(
        owner_id=user.id,
        project_code=code,
        name=body.name.strip(),
        target_name=body.target_name.strip(),
        description=body.description,
    )
    db.add(project)
    db.flush()
    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role=ProjectRole.owner.value,
        )
    )
    add_audit(
        db,
        project_id=project.id,
        entity_type="project",
        entity_id=project.id,
        action="create",
        actor_id=user.id,
        after=model_snapshot(project),
    )
    return project


def update_project(
    db: Session,
    project: AntibodyProject,
    body: ProjectUpdate,
    user: User,
) -> AntibodyProject:
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in PROJECT_STATUSES:
        raise HTTPException(400, "项目状态无效")
    before = model_snapshot(project)
    for field, value in changes.items():
        if isinstance(value, str) and field in {"name", "target_name"}:
            value = value.strip()
        setattr(project, field, value)
    if project.status == ProjectStatus.archived.value:
        project.archived_at = datetime.now(timezone.utc)
    elif "status" in changes:
        project.archived_at = None
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="project",
        entity_id=project.id,
        action="update",
        actor_id=user.id,
        before=before,
        after=model_snapshot(project),
    )
    return project


def add_project_member(
    db: Session,
    project: AntibodyProject,
    username: str,
    role: str,
    actor: User,
) -> tuple[ProjectMember, User]:
    target = db.scalar(select(User).where(User.username == username.strip()))
    if not target or not target.is_active:
        raise HTTPException(404, "找不到可用的用户")
    if target.id == project.owner_id:
        raise HTTPException(409, "项目负责人已经是项目成员")
    existing = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == target.id,
        )
    )
    if existing:
        raise HTTPException(409, "该用户已经在项目中")
    member = ProjectMember(project_id=project.id, user_id=target.id, role=role)
    db.add(member)
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="project_member",
        entity_id=member.id,
        action="create",
        actor_id=actor.id,
        after={"user_id": target.id, "username": target.username, "role": role},
    )
    return member, target


def get_candidate(
    db: Session, project_id: str, candidate_id: str
) -> AntibodyCandidate:
    candidate = db.get(AntibodyCandidate, candidate_id)
    if not candidate or candidate.project_id != project_id:
        raise HTTPException(404, "候选抗体不存在")
    return candidate


def get_version(
    db: Session, project_id: str, version_id: str
) -> AntibodyVersion:
    version = db.get(AntibodyVersion, version_id)
    if not version:
        raise HTTPException(404, "序列版本不存在")
    candidate = db.get(AntibodyCandidate, version.candidate_id)
    if not candidate or candidate.project_id != project_id:
        raise HTTPException(404, "序列版本不存在")
    return version


def _normalized_chains(
    antibody_type: str, chains: list[VersionChainInput]
) -> dict[str, tuple[str, str | None, str | None, str | None]]:
    normalized = {}
    for chain in chains:
        role = chain.chain_role.strip().upper()
        if role in normalized:
            raise HTTPException(400, f"链角色重复: {role}")
        try:
            variable, translated_cds = protein_and_optional_cds(chain.variable_sequence)
            full = normalize_sequence(chain.full_sequence) if chain.full_sequence else None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        nucleotide = None
        if chain.nucleotide_sequence:
            nucleotide = re.sub(r"[^A-Za-z]", "", chain.nucleotide_sequence).upper().replace("U", "T")
        elif translated_cds:
            nucleotide = translated_cds
        normalized[role] = (variable, full, chain.chain_name, nucleotide)

    required = {"VH", "VL"} if antibody_type == "igg" else {"VHH"}
    if set(normalized) != required:
        expected = "VH 和 VL" if antibody_type == "igg" else "VHH"
        raise HTTPException(400, f"{antibody_type.upper()} 必须且只能提供 {expected}")
    return normalized


def _annotation_for(sequence: str) -> dict | None:
    return annotate_antibody_chain(sequence)


def _add_chain_rows(
    db: Session,
    version: AntibodyVersion,
    chains: dict[str, tuple[str, str | None, str | None, str | None]],
) -> dict[str, dict | None]:
    annotations = {}
    for role, (variable, full, name, nucleotide) in chains.items():
        annotation = _annotation_for(variable)
        annotations[role] = annotation
        db.add(
            AntibodyVersionChain(
                version_id=version.id,
                chain_role=role,
                chain_name=name,
                variable_sequence=variable,
                full_sequence=full,
                nucleotide_sequence=nucleotide,
                sequence_hash=sequence_sha256(variable),
                numbering_scheme="kabat",
                annotation_json=annotation,
                annotation_tool="ANARCI" if annotation else None,
            )
        )
    return annotations


def _region_and_kabat(
    annotation: dict | None, sequence_position: int | None
) -> tuple[str | None, str | None]:
    if not annotation or not sequence_position:
        return None, None
    index = sequence_position - 1
    region = "FW"
    for span in annotation.get("cdr_spans", []):
        if span["start"] <= index <= span["end"]:
            region = span["name"]
            break
    labels = annotation.get("kabat_labels", [])
    kabat = labels[index] if 0 <= index < len(labels) else None
    return region, kabat


def _replace_generated_mutations(
    db: Session,
    version: AntibodyVersion,
    parent: AntibodyVersion,
    chains: dict[str, tuple[str, str | None, str | None, str | None]],
    annotations: dict[str, dict | None],
) -> None:
    db.execute(delete(VersionMutation).where(VersionMutation.version_id == version.id))
    parent_rows = db.scalars(
        select(AntibodyVersionChain).where(AntibodyVersionChain.version_id == parent.id)
    ).all()
    parent_chains = {row.chain_role: row.variable_sequence for row in parent_rows}
    if set(parent_chains) != set(chains):
        raise HTTPException(400, "子版本的链角色必须与父版本一致")

    for role, (target, _full, _name, _nucleotide) in chains.items():
        for difference in diff_sequences(parent_chains[role], target):
            region, kabat = _region_and_kabat(
                annotations.get(role), difference["sequence_position"]
            )
            db.add(
                VersionMutation(
                    version_id=version.id,
                    parent_version_id=parent.id,
                    chain_role=role,
                    numbering_label=str(difference["sequence_position"]),
                    kabat_label=kabat,
                    region=region,
                    rationale=version.rationale,
                    **difference,
                )
            )


def version_snapshot(db: Session, version: AntibodyVersion) -> dict:
    """审计用完整版本快照，序列变化不能只留下哈希。"""
    snapshot = model_snapshot(version)
    chains = db.scalars(
        select(AntibodyVersionChain)
        .where(AntibodyVersionChain.version_id == version.id)
        .order_by(AntibodyVersionChain.chain_role)
    ).all()
    mutations = db.scalars(
        select(VersionMutation)
        .where(VersionMutation.version_id == version.id)
        .order_by(VersionMutation.chain_role, VersionMutation.sequence_position)
    ).all()
    snapshot["chains"] = [model_snapshot(item) for item in chains]
    snapshot["mutations"] = [model_snapshot(item) for item in mutations]
    return snapshot


def create_candidate_with_wt(
    db: Session,
    project: AntibodyProject,
    body: CandidateCreate,
    user: User,
) -> tuple[AntibodyCandidate, AntibodyVersion]:
    code = body.candidate_code.strip()
    if db.scalar(
        select(AntibodyCandidate.id).where(
            AntibodyCandidate.project_id == project.id,
            AntibodyCandidate.candidate_code == code,
        )
    ):
        raise HTTPException(409, "项目内候选抗体编号不能重复")
    chains = _normalized_chains(body.antibody_type, body.chains)
    candidate = AntibodyCandidate(
        project_id=project.id,
        candidate_code=code,
        name=body.name.strip(),
        antibody_category=body.antibody_category,
        antibody_type=body.antibody_type,
        description=body.description,
        created_by=user.id,
    )
    db.add(candidate)
    db.flush()
    wt = AntibodyVersion(
        candidate_id=candidate.id,
        version_code="WT",
        version_number=0,
        name=body.wt_name,
        status=VersionStatus.locked.value,
        sequence_hash=version_sha256(
            {role: values[0] for role, values in chains.items()}
        ),
        created_by=user.id,
        locked_at=datetime.now(timezone.utc),
    )
    db.add(wt)
    db.flush()
    _add_chain_rows(db, wt, chains)
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="candidate",
        entity_id=candidate.id,
        action="create",
        actor_id=user.id,
        after={"candidate": model_snapshot(candidate), "wt": version_snapshot(db, wt)},
    )
    return candidate, wt


def set_candidate_category(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    category: str,
    user: User,
) -> AntibodyCandidate:
    """旧候选允许补录一次；固定分类一旦设置便不能改动。"""
    if candidate.antibody_category:
        if candidate.antibody_category == category:
            return candidate
        raise HTTPException(409, "RM/RN/RL 分类设置后不能修改")
    before = model_snapshot(candidate)
    candidate.antibody_category = category
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="candidate",
        entity_id=candidate.id,
        action="classify",
        actor_id=user.id,
        before=before,
        after=model_snapshot(candidate),
    )
    return candidate


def _require_parent(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    parent_version_id: str,
) -> AntibodyVersion:
    parent = get_version(db, project.id, parent_version_id)
    if parent.candidate_id != candidate.id:
        raise HTTPException(400, "父版本不属于当前候选抗体")
    if parent.status not in EDITABLE_PARENT_STATUSES:
        raise HTTPException(409, "请先锁定父版本")
    return parent


def _lock_candidate(db: Session, candidate_id: str) -> None:
    db.execute(
        select(AntibodyCandidate)
        .where(AntibodyCandidate.id == candidate_id)
        .with_for_update()
    )


def _parse_fasta_records(text: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    header = ""
    chunks: list[str] = []

    def flush() -> None:
        sequence = re.sub(r"[^A-Za-z]", "", "".join(chunks)).upper()
        if sequence:
            records.append((header.strip() or f"seq{len(records) + 1}", sequence))

    for line in (text or "").replace("\r", "").split("\n"):
        value = line.strip()
        if not value:
            continue
        if value.startswith(">"):
            if chunks or header:
                flush()
            header = value[1:].strip()
            chunks = []
        else:
            chunks.append(value)
    if chunks or header:
        flush()
    return records


def _fasta_header_role(header: str) -> tuple[str, str | None]:
    tokens = [part for part in re.split(r"[\s|]+", header) if part]
    if not tokens:
        return "seq", None
    matched = _FASTA_ROLE.match(tokens[0])
    if matched:
        return matched.group("base").rstrip("_-./|"), _FASTA_ROLE_TOKEN[
            matched.group("role").upper()
        ]
    if len(tokens) >= 2 and tokens[-1].upper() in _FASTA_ROLE_TOKEN:
        return tokens[0], _FASTA_ROLE_TOKEN[tokens[-1].upper()]
    return tokens[0], None


def _clip_name(value: str | None) -> str | None:
    text = (value or "").strip()
    return text[:160] or None


def _protein_sequence(sequence: str) -> tuple[str, str | None] | None:
    try:
        return protein_and_optional_cds(sequence)
    except ValueError:
        return None


def fasta_to_import_items(
    antibody_type: str, text: str
) -> list[VersionImportItem]:
    if ">" not in (text or ""):
        raise HTTPException(400, "FASTA 需要以 > 开头的标题行")
    records = _parse_fasta_records(text)
    kept = []
    skipped = 0
    for header, sequence in records:
        resolved = _protein_sequence(sequence)
        if resolved is None:
            skipped += 1
            continue
        kept.append((header, resolved[0], resolved[1]))
    if not kept:
        raise HTTPException(400, "FASTA 里没有可导入的氨基酸或核酸 CDS")
    records = kept
    if antibody_type == "vhh":
        items: list[VersionImportItem] = []
        for header, sequence, nucleotide in records:
            base, role = _fasta_header_role(header)
            if role in {"VH", "VL"}:
                raise HTTPException(
                    400,
                    "当前候选是 VHH，请使用每条一个标题的 FASTA，不要成对标注 VH/VL",
                )
            items.append(
                VersionImportItem(
                    name=_clip_name(base),
                    chains=[
                        VersionChainInput(
                            chain_role="VHH",
                            variable_sequence=sequence,
                            nucleotide_sequence=nucleotide,
                        )
                    ],
                )
            )
        if len(items) > 200:
            raise HTTPException(400, "一次最多导入 200 条")
        return items

    grouped: dict[str, dict[str, tuple[str, str | None]]] = {}
    order: list[str] = []
    for header, sequence, nucleotide in records:
        base, role = _fasta_header_role(header)
        if role not in {"VH", "VL"}:
            raise HTTPException(
                400,
                "IgG FASTA 需要成对标题，例如 >clone_27_VH 与 >clone_27_VL",
            )
        if base not in grouped:
            grouped[base] = {}
            order.append(base)
        if role in grouped[base]:
            raise HTTPException(400, f"{base} 的 {role} 在 FASTA 中重复")
        grouped[base][role] = (sequence, nucleotide)

    items = []
    for base in order:
        slot = grouped[base]
        missing = {"VH", "VL"} - set(slot)
        if missing:
            raise HTTPException(400, f"{base} 缺少 {'/'.join(sorted(missing))}")
        items.append(
            VersionImportItem(
                name=_clip_name(base),
                chains=[
                    VersionChainInput(
                        chain_role="VH",
                        variable_sequence=slot["VH"][0],
                        nucleotide_sequence=slot["VH"][1],
                    ),
                    VersionChainInput(
                        chain_role="VL",
                        variable_sequence=slot["VL"][0],
                        nucleotide_sequence=slot["VL"][1],
                    ),
                ],
            )
        )
    if len(items) > 200:
        raise HTTPException(400, "一次最多导入 200 条")
    return items


def decode_fasta_upload(raw: bytes, filename: str | None) -> str:
    if len(raw) > _MAX_FASTA_BYTES:
        raise HTTPException(400, "FASTA 文件超过 2MB")
    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in {".fa", ".fasta", ".fas", ".fna", ".txt"}:
        raise HTTPException(400, "请上传 .fa / .fasta 文件")
    if not raw.strip():
        raise HTTPException(400, "FASTA 文件为空")
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(400, "无法读取 FASTA 文件编码")


def _assert_unique_sequence(
    db: Session, candidate_id: str, sequence_hash: str
) -> None:
    exists = db.scalar(
        select(AntibodyVersion.id).where(
            AntibodyVersion.candidate_id == candidate_id,
            AntibodyVersion.sequence_hash == sequence_hash,
        )
    )
    if exists:
        raise HTTPException(409, "该序列已作为版本存在")


def create_version(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    body: VersionCreate,
    user: User,
) -> AntibodyVersion:
    parent = _require_parent(db, project, candidate, body.parent_version_id)
    _lock_candidate(db, candidate.id)
    chains = _normalized_chains(candidate.antibody_type, body.chains)
    sequence_hash = version_sha256({role: values[0] for role, values in chains.items()})
    _assert_unique_sequence(db, candidate.id, sequence_hash)
    version_code, version_number = _allocate_engineered_code(db, candidate.id, parent)
    version = AntibodyVersion(
        candidate_id=candidate.id,
        primary_parent_id=parent.id,
        version_code=version_code,
        version_number=version_number,
        name=(body.name.strip() or None) if body.name else None,
        purpose=body.purpose,
        rationale=body.rationale,
        evidence=body.evidence,
        status=VersionStatus.draft.value,
        sequence_hash=sequence_hash,
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    annotations = _add_chain_rows(db, version, chains)
    _replace_generated_mutations(db, version, parent, chains, annotations)
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="antibody_version",
        entity_id=version.id,
        action="create",
        actor_id=user.id,
        after=version_snapshot(db, version),
    )
    return version


def import_versions(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    body: VersionImportRequest,
    user: User,
) -> list[AntibodyVersion]:
    parent = _require_parent(db, project, candidate, body.parent_version_id)
    _lock_candidate(db, candidate.id)
    seen_hashes: set[str] = set()
    created: list[AntibodyVersion] = []
    for index, item in enumerate(body.items, start=1):
        chains = _normalized_chains(candidate.antibody_type, item.chains)
        sequence_hash = version_sha256(
            {role: values[0] for role, values in chains.items()}
        )
        if sequence_hash in seen_hashes:
            raise HTTPException(400, f"第 {index} 条与本次导入中的其他序列重复")
        seen_hashes.add(sequence_hash)
        _assert_unique_sequence(db, candidate.id, sequence_hash)
        created.append(
            create_version(
                db,
                project,
                candidate,
                VersionCreate(
                    parent_version_id=parent.id,
                    name=item.name,
                    chains=item.chains,
                ),
                user,
            )
        )
    return created


def import_versions_from_fasta(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    parent_version_id: str,
    raw: bytes,
    filename: str | None,
    user: User,
) -> list[AntibodyVersion]:
    text = decode_fasta_upload(raw, filename)
    items = fasta_to_import_items(candidate.antibody_type, text)
    return import_versions(
        db,
        project,
        candidate,
        VersionImportRequest(parent_version_id=parent_version_id, items=items),
        user,
    )


def _header_key(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", (value or "").strip()).lower()


def _find_column(headers: list[str], aliases: set[str]) -> int | None:
    for index, header in enumerate(headers):
        if _header_key(header) in aliases:
            return index
    return None


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _chain_from_sequence(role: str, raw: str, row_label: str) -> VersionChainInput:
    try:
        protein, cds = protein_and_optional_cds(raw)
    except ValueError as exc:
        raise HTTPException(400, f"{row_label}：{exc}") from exc
    return VersionChainInput(
        chain_role=role,
        variable_sequence=protein,
        nucleotide_sequence=cds,
    )


def xlsx_to_import_items(antibody_type: str, raw: bytes, filename: str | None) -> list[VersionImportItem]:
    if len(raw) > _MAX_TABLE_BYTES:
        raise HTTPException(400, "表格文件超过 8MB")
    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(400, "请上传 .xlsx 表格")
    matrix = read_xlsx_matrix(raw)
    header_index = 0
    for index, row in enumerate(matrix[:8]):
        joined = "".join(row)
        if "蛋白名称" in joined or "基因序列" in joined or "基因名称" in joined:
            header_index = index
            break
    headers = matrix[header_index]
    name_col = _find_column(headers, _NAME_HEADERS)
    seq_col = _find_column(headers, _SEQ_HEADERS)
    gene_col = _find_column(headers, _GENE_HEADERS)
    vh_col = _find_column(headers, _VH_HEADERS)
    vl_col = _find_column(headers, _VL_HEADERS)
    data_rows = [
        (header_index + 1 + offset, row)
        for offset, row in enumerate(matrix[header_index + 1 :])
        if any(str(cell).strip() for cell in row)
    ]
    if not data_rows:
        raise HTTPException(400, "表格没有数据行")

    if antibody_type == "vhh":
        if seq_col is None:
            raise HTTPException(400, "表格需要「基因序列」列")
        items: list[VersionImportItem] = []
        for excel_row, row in data_rows:
            name = _cell(row, name_col) or _cell(row, gene_col)
            sequence = _cell(row, seq_col)
            if not sequence:
                continue
            if not name:
                raise HTTPException(400, f"第 {excel_row} 行缺少蛋白名称")
            items.append(
                VersionImportItem(
                    name=_clip_name(name),
                    chains=[_chain_from_sequence("VHH", sequence, f"第 {excel_row} 行 {name}")],
                )
            )
        if not items:
            raise HTTPException(400, "表格里没有可导入的基因序列")
        if len(items) > 200:
            raise HTTPException(400, "一次最多导入 200 条")
        return items

    if vh_col is None or vl_col is None:
        raise HTTPException(
            400,
            "当前候选是 IgG，表格需要「VH序列」和「VL序列」两列；VHH 基因表请在 VHH 候选下导入",
        )
    items = []
    for excel_row, row in data_rows:
        name = _cell(row, name_col) or _cell(row, gene_col)
        vh = _cell(row, vh_col)
        vl = _cell(row, vl_col)
        if not vh and not vl:
            continue
        if not name:
            raise HTTPException(400, f"第 {excel_row} 行缺少蛋白名称")
        if not vh or not vl:
            raise HTTPException(400, f"第 {excel_row} 行 {name} 需要同时提供 VH 和 VL")
        items.append(
            VersionImportItem(
                name=_clip_name(name),
                chains=[
                    _chain_from_sequence("VH", vh, f"第 {excel_row} 行 {name} VH"),
                    _chain_from_sequence("VL", vl, f"第 {excel_row} 行 {name} VL"),
                ],
            )
        )
    if not items:
        raise HTTPException(400, "表格里没有可导入的基因序列")
    if len(items) > 200:
        raise HTTPException(400, "一次最多导入 200 条")
    return items


def import_versions_from_xlsx(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    parent_version_id: str,
    raw: bytes,
    filename: str | None,
    user: User,
) -> list[AntibodyVersion]:
    items = xlsx_to_import_items(candidate.antibody_type, raw, filename)
    return import_versions(
        db,
        project,
        candidate,
        VersionImportRequest(parent_version_id=parent_version_id, items=items),
        user,
    )


def update_draft_version(
    db: Session,
    project: AntibodyProject,
    version: AntibodyVersion,
    body: VersionUpdate,
    user: User,
) -> AntibodyVersion:
    if version.status != VersionStatus.draft.value:
        raise HTTPException(409, "只有草稿版本可以修改")
    before = version_snapshot(db, version)
    changes = body.model_dump(exclude_unset=True, exclude={"chains"})
    for field, value in changes.items():
        setattr(version, field, value)

    if body.chains is not None:
        candidate = db.get(AntibodyCandidate, version.candidate_id)
        parent = db.get(AntibodyVersion, version.primary_parent_id)
        chains = _normalized_chains(candidate.antibody_type, body.chains)
        version.sequence_hash = version_sha256(
            {role: values[0] for role, values in chains.items()}
        )
        db.execute(
            delete(AntibodyVersionChain).where(
                AntibodyVersionChain.version_id == version.id
            )
        )
        annotations = _add_chain_rows(db, version, chains)
        _replace_generated_mutations(db, version, parent, chains, annotations)

    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="antibody_version",
        entity_id=version.id,
        action="update",
        actor_id=user.id,
        before=before,
        after=version_snapshot(db, version),
    )
    return version


def lock_version(
    db: Session,
    project: AntibodyProject,
    version: AntibodyVersion,
    user: User,
) -> AntibodyVersion:
    if version.status != VersionStatus.draft.value:
        raise HTTPException(409, "只有草稿版本可以锁定")
    before = version_snapshot(db, version)
    version.status = VersionStatus.locked.value
    version.locked_at = datetime.now(timezone.utc)
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="antibody_version",
        entity_id=version.id,
        action="lock",
        actor_id=user.id,
        before=before,
        after=version_snapshot(db, version),
    )
    return version


def _matches_round(version_code: str, round_code: str) -> bool:
    if round_code.upper() == "WT":
        return version_code.upper() == "WT"
    return version_code == round_code or version_code.startswith(f"{round_code}-")


def lock_draft_versions(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    round_code: str | None,
    user: User,
) -> list[AntibodyVersion]:
    rows = db.scalars(
        select(AntibodyVersion)
        .where(
            AntibodyVersion.candidate_id == candidate.id,
            AntibodyVersion.status == VersionStatus.draft.value,
        )
        .order_by(AntibodyVersion.version_number)
    ).all()
    if round_code:
        rows = [item for item in rows if _matches_round(item.version_code, round_code)]
    else:
        rows = [item for item in rows if item.version_code.upper() != "WT"]
    if not rows:
        raise HTTPException(400, "没有可锁定的草稿版本")
    return [lock_version(db, project, item, user) for item in rows]


def version_out(db: Session, version: AntibodyVersion) -> VersionOut:
    chains = db.scalars(
        select(AntibodyVersionChain)
        .where(AntibodyVersionChain.version_id == version.id)
        .order_by(AntibodyVersionChain.chain_role)
    ).all()
    mutations = db.scalars(
        select(VersionMutation)
        .where(VersionMutation.version_id == version.id)
        .order_by(
            VersionMutation.chain_role,
            VersionMutation.sequence_position,
            VersionMutation.created_at,
        )
    ).all()
    payload = model_snapshot(version)
    payload["chains"] = chains
    payload["mutations"] = mutations
    return VersionOut.model_validate(payload)


def create_sample_batch(
    db: Session,
    project: AntibodyProject,
    body: SampleBatchCreate,
    user: User,
) -> SampleBatch:
    version = get_version(db, project.id, body.version_id)
    if version.status == VersionStatus.draft.value:
        raise HTTPException(409, "草稿版本不能创建样品批次")
    if db.scalar(
        select(SampleBatch.id).where(
            SampleBatch.version_id == version.id,
            SampleBatch.batch_code == body.batch_code.strip(),
        )
    ):
        raise HTTPException(409, "该版本已经使用这个样品批次号")
    sample = SampleBatch(
        version_id=version.id,
        operator_id=user.id,
        **{
            **body.model_dump(exclude={"version_id"}),
            "batch_code": body.batch_code.strip(),
        },
    )
    db.add(sample)
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="sample_batch",
        entity_id=sample.id,
        action="create",
        actor_id=user.id,
        after=model_snapshot(sample),
    )
    return sample


def create_experiment(
    db: Session,
    project: AntibodyProject,
    body: ExperimentCreate,
    user: User,
) -> ExperimentRecord:
    version = get_version(db, project.id, body.version_id)
    if version.status == VersionStatus.draft.value:
        raise HTTPException(409, "草稿版本不能录入实验")
    if body.sample_batch_id:
        sample = db.get(SampleBatch, body.sample_batch_id)
        if not sample or sample.version_id != version.id:
            raise HTTPException(400, "样品批次与实验版本不匹配")
    for value in body.measurements:
        if value.value_numeric is None and value.value_text is None:
            raise HTTPException(400, f"指标 {value.metric_name} 缺少结果值")

    experiment = ExperimentRecord(
        project_id=project.id,
        version_id=version.id,
        operator_id=user.id,
        **body.model_dump(exclude={"version_id", "measurements"}),
    )
    db.add(experiment)
    db.flush()
    for value in body.measurements:
        db.add(
            ExperimentMeasurement(
                experiment_id=experiment.id,
                **value.model_dump(),
            )
        )
    if version.status == VersionStatus.locked.value:
        before_version = version_snapshot(db, version)
        version.status = VersionStatus.tested.value
        db.flush()
        add_audit(
            db,
            project_id=project.id,
            entity_type="antibody_version",
            entity_id=version.id,
            action="mark_tested",
            actor_id=user.id,
            before=before_version,
            after=version_snapshot(db, version),
        )
    add_audit(
        db,
        project_id=project.id,
        entity_type="experiment",
        entity_id=experiment.id,
        action="create",
        actor_id=user.id,
        after=model_snapshot(experiment),
    )
    return experiment


def _parse_optional_number(raw: str) -> float | None:
    value, _qualifier = _parse_reported_number(raw)
    return value


def _parse_reported_number(raw: str) -> tuple[float | None, str | None]:
    text = str(raw or "").strip()
    if not text or text.lower() in _BLANK_NUMBER:
        return None, None
    qualifier: str | None = None
    for prefix in ("<=", ">=", "≤", "≥", "<", ">", "＜", "＞"):
        if text.startswith(prefix):
            qualifier = _LIMIT_PREFIX[prefix]
            text = text[len(prefix) :].strip()
            break
    text = (
        text.replace(",", "")
        .replace("×10^", "e")
        .replace("x10^", "e")
        .replace("×10", "e")
        .replace("x10", "e")
    )
    try:
        return float(text), qualifier
    except ValueError:
        return None, None


def _normalize_result(raw: str) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"positive", "pos", "+", "阳性"}:
        return "Positive"
    if lowered in {"negative", "neg", "-", "阴性"}:
        return "Negative"
    return text


def _protein_key_from_loading_id(raw: str) -> str:
    text = str(raw or "").strip()
    return re.sub(r"^\d{1,4}[-_／/]", "", text).strip()


def _is_control_sample(loading_id: str, protein_key: str) -> bool:
    blob = f"{loading_id} {protein_key}"
    return bool(_CONTROL_RE.search(blob))


def _match_version_by_protein_name(
    protein_key: str, versions: list[AntibodyVersion]
) -> AntibodyVersion | None:
    key = protein_key.strip().lower()
    if not key:
        return None
    named = [(item, (item.name or "").strip()) for item in versions if (item.name or "").strip()]
    exact = [item for item, name in named if name.lower() == key]
    if len(exact) == 1:
        return exact[0]
    contained = [item for item, name in named if key in name.lower() or name.lower() in key]
    if len(contained) == 1:
        return contained[0]
    return None


def _affinity_experiment_map(
    db: Session, version_ids: list[str]
) -> dict[tuple[str, str, str], ExperimentRecord]:
    if not version_ids:
        return {}
    rows = db.scalars(
        select(ExperimentRecord).where(
            ExperimentRecord.version_id.in_(version_ids),
            ExperimentRecord.experiment_type == "affinity",
        )
    ).all()
    keyed: dict[tuple[str, str, str], ExperimentRecord] = {}
    for item in rows:
        conditions = item.conditions_json or {}
        keyed[
            (
                item.version_id,
                str(conditions.get("antigen") or ""),
                str(conditions.get("loading_sample_id") or ""),
            )
        ] = item
    return keyed


def preview_affinity_xlsx(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    raw: bytes,
    filename: str | None,
) -> AffinityPreviewOut:
    if len(raw) > _MAX_TABLE_BYTES:
        raise HTTPException(400, "表格文件超过 8MB")
    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(400, "请上传 .xlsx 表格")
    matrix = read_xlsx_matrix(raw, _AFFINITY_SHEET)
    header_index = 0
    for index, row in enumerate(matrix[:8]):
        joined = _header_key("".join(row))
        if "loadingsampleid" in joined or "上样" in "".join(row):
            header_index = index
            break
    headers = [_header_key(item) for item in matrix[header_index]]
    loading_col = _find_column(matrix[header_index], _LOADING_ID_HEADERS)
    antigen_col = _find_column(matrix[header_index], _ANTIGEN_HEADERS)
    kd_col = _find_column(matrix[header_index], _KD_HEADERS)
    if loading_col is None or antigen_col is None:
        raise HTTPException(400, "「亲和力」表需要 Loading Sample ID 和 Sample ID（抗原）两列")
    if kd_col is None:
        raise HTTPException(400, "「亲和力」表需要 KD 列")
    loading_resp_col = _find_column(matrix[header_index], _LOADING_RESP_HEADERS)
    resp_col = _find_column(matrix[header_index], _RESP_HEADERS)
    ka_col = _find_column(matrix[header_index], _KA_HEADERS)
    kdis_col = _find_column(matrix[header_index], _KDIS_HEADERS)
    result_col = _find_column(matrix[header_index], _RESULT_HEADERS)

    versions = db.scalars(
        select(AntibodyVersion)
        .where(AntibodyVersion.candidate_id == candidate.id)
        .order_by(AntibodyVersion.version_number)
    ).all()
    existing = _affinity_experiment_map(db, [item.id for item in versions])
    preview_rows: list[AffinityPreviewRow] = []
    for offset, row in enumerate(matrix[header_index + 1 :]):
        excel_row = header_index + 2 + offset
        loading_id = _cell(row, loading_col)
        antigen = _cell(row, antigen_col)
        if not loading_id and not antigen:
            continue
        protein_key = _protein_key_from_loading_id(loading_id)
        result = _normalize_result(_cell(row, result_col))
        kd_m, kd_qualifier = _parse_reported_number(_cell(row, kd_col))
        ka, ka_qualifier = _parse_reported_number(_cell(row, ka_col))
        kdis, kdis_qualifier = _parse_reported_number(_cell(row, kdis_col))
        parsed = AffinityPreviewRow(
            excel_row=excel_row,
            loading_sample_id=loading_id,
            protein_key=protein_key,
            antigen=antigen,
            loading_response=_parse_optional_number(_cell(row, loading_resp_col)),
            response=_parse_optional_number(_cell(row, resp_col)),
            kd_m=kd_m,
            kd_qualifier=kd_qualifier,
            ka=ka,
            ka_qualifier=ka_qualifier,
            kdis=kdis,
            kdis_qualifier=kdis_qualifier,
            result=result,
            status="unmatched",
        )
        if _is_control_sample(loading_id, protein_key):
            parsed.status = "control"
            parsed.message = "对照行，默认不导入"
            preview_rows.append(parsed)
            continue
        matched = _match_version_by_protein_name(protein_key, versions)
        if matched:
            parsed.version_id = matched.id
            parsed.version_code = matched.version_code
            parsed.version_name = matched.name
            if matched.status == VersionStatus.draft.value:
                parsed.status = "draft"
                parsed.message = f"{matched.version_code} 仍是草稿，请先锁定再导入实验"
            elif (matched.id, antigen, loading_id) in existing:
                parsed.status = "duplicate"
                parsed.selected = True
                parsed.message = "已经导入过，再次导入会用表中的新值覆盖"
            else:
                parsed.status = "matched"
                parsed.selected = True
        else:
            parsed.message = "没有对上蛋白名称，可在预览里指定版本"
        preview_rows.append(parsed)

    if not preview_rows:
        raise HTTPException(400, "「亲和力」表没有可读取的数据行")
    if len(preview_rows) > 200:
        raise HTTPException(400, "一次最多预览 200 行")
    return AffinityPreviewOut(
        sheet_name=_AFFINITY_SHEET,
        rows=preview_rows,
        matched=sum(item.status == "matched" for item in preview_rows),
        unmatched=sum(item.status == "unmatched" for item in preview_rows),
        control=sum(item.status == "control" for item in preview_rows),
        duplicate=sum(item.status == "duplicate" for item in preview_rows),
    )


def _affinity_summary(item: AffinityImportItem) -> str | None:
    if item.kd_m is not None:
        prefix = item.kd_qualifier or ""
        return f"{item.result or 'Positive'} · {item.antigen} · KD={prefix}{item.kd_m:.3e} M"
    if item.result:
        return f"{item.result} · {item.antigen}"
    return None


def _affinity_measurements(item: AffinityImportItem) -> list[MeasurementInput]:
    rows: list[MeasurementInput] = []
    if item.kd_m is not None:
        rows.append(
            MeasurementInput(
                metric_name="KD",
                value_numeric=item.kd_m,
                unit="M",
                qualifier=item.kd_qualifier,
            )
        )
    elif item.result == "Negative":
        rows.append(MeasurementInput(metric_name="KD", value_text="NB", unit="M", qualifier="NB"))
    if item.ka is not None:
        rows.append(
            MeasurementInput(
                metric_name="ka",
                value_numeric=item.ka,
                unit="1/Ms",
                qualifier=item.ka_qualifier,
            )
        )
    if item.kdis is not None:
        rows.append(
            MeasurementInput(
                metric_name="kdis",
                value_numeric=item.kdis,
                unit="1/s",
                qualifier=item.kdis_qualifier,
            )
        )
    if item.loading_response is not None:
        rows.append(MeasurementInput(metric_name="loading_response", value_numeric=item.loading_response))
    if item.response is not None:
        rows.append(MeasurementInput(metric_name="response", value_numeric=item.response))
    if item.result:
        rows.append(MeasurementInput(metric_name="result", value_text=item.result))
    if not rows:
        raise HTTPException(400, f"第 {item.excel_row} 行没有可保存的测量值")
    return rows


def _replace_affinity_measurements(
    db: Session,
    experiment: ExperimentRecord,
    item: AffinityImportItem,
    user: User,
) -> ExperimentRecord:
    before = model_snapshot(experiment)
    db.execute(delete(ExperimentMeasurement).where(ExperimentMeasurement.experiment_id == experiment.id))
    experiment.result_summary = _affinity_summary(item)
    experiment.updated_at = datetime.now(timezone.utc)
    db.flush()
    for value in _affinity_measurements(item):
        db.add(ExperimentMeasurement(experiment_id=experiment.id, **value.model_dump()))
    add_audit(
        db,
        project_id=experiment.project_id,
        entity_type="experiment",
        entity_id=experiment.id,
        action="update",
        actor_id=user.id,
        before=before,
        after=model_snapshot(experiment),
    )
    db.flush()
    db.refresh(experiment)
    return experiment


def import_affinity_xlsx(
    db: Session,
    project: AntibodyProject,
    candidate: AntibodyCandidate,
    body: AffinityImportRequest,
    user: User,
) -> list[ExperimentRecord]:
    versions = {
        item.id: item
        for item in db.scalars(
            select(AntibodyVersion).where(AntibodyVersion.candidate_id == candidate.id)
        ).all()
    }
    existing = _affinity_experiment_map(db, list(versions))
    saved: list[ExperimentRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for item in body.items:
        version = versions.get(item.version_id)
        if not version:
            raise HTTPException(400, f"第 {item.excel_row} 行指定的版本不属于当前候选抗体")
        key = (item.version_id, item.antigen, item.loading_sample_id)
        if key in seen:
            raise HTTPException(400, f"第 {item.excel_row} 行在本次导入中重复：{item.antigen}")
        seen.add(key)
        if key in existing:
            saved.append(_replace_affinity_measurements(db, existing[key], item, user))
            continue
        saved.append(
            create_experiment(
                db,
                project,
                ExperimentCreate(
                    version_id=version.id,
                    title=_clip_name(f"{item.antigen} · {item.protein_key or item.loading_sample_id}") or item.antigen,
                    experiment_type="affinity",
                    conditions_json={
                        "antigen": item.antigen,
                        "loading_sample_id": item.loading_sample_id,
                        "protein_key": item.protein_key,
                        "source": "affinity-xlsx",
                    },
                    result_summary=_affinity_summary(item),
                    measurements=_affinity_measurements(item),
                ),
                user,
            )
        )
    return saved


def create_job_link(
    db: Session,
    project: AntibodyProject,
    body: JobLinkCreate,
    user: User,
) -> ProjectJobLink:
    version = get_version(db, project.id, body.version_id)
    job = db.get(Job, body.job_id)
    if not job or (job.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "计算任务不存在或你无权访问")
    existing = db.scalar(
        select(ProjectJobLink.id).where(
            ProjectJobLink.version_id == version.id,
            ProjectJobLink.original_job_id == job.id,
        )
    )
    if existing:
        raise HTTPException(409, "该任务已经关联到这个版本")
    link = ProjectJobLink(
        project_id=project.id,
        version_id=version.id,
        job_id=job.id,
        original_job_id=job.id,
        engine=job.engine,
        purpose=body.purpose,
        input_sequence_hash=job.sequence_hash,
        params_snapshot=job.params_json,
        result_snapshot=job.results_json,
        linked_by=user.id,
    )
    db.add(link)
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="job_link",
        entity_id=link.id,
        action="create",
        actor_id=user.id,
        after=model_snapshot(link),
    )
    return link
