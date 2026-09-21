"""抗体改造项目 API。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.models import User
from app.modules.antibody_projects.access import (
    add_audit,
    model_snapshot,
    project_access,
    visible_projects,
)
from app.modules.antibody_projects.models import (
    AntibodyCandidate,
    AntibodyVersion,
    AuditEvent,
    ExperimentMeasurement,
    ExperimentRecord,
    ProjectArtifact,
    ProjectJobLink,
    ProjectMember,
    ProjectRole,
    SampleBatch,
    VersionMutation,
)
from app.modules.antibody_projects.provenance import diff_sequences
from app.modules.antibody_projects.service import (
    add_project_member,
    create_candidate_with_wt,
    create_experiment,
    create_job_link,
    create_project,
    create_sample_batch,
    create_version,
    get_candidate,
    get_version,
    import_versions,
    import_versions_from_fasta,
    import_versions_from_xlsx,
    import_affinity_xlsx,
    preview_affinity_xlsx,
    lock_draft_versions,
    lock_version,
    set_candidate_category,
    update_draft_version,
    update_project,
    version_out,
)
from app.modules.antibody_projects.storage import project_storage_dir, sha256_file
from app.schemas.antibody_project import (
    AffinityImportRequest,
    AffinityPreviewOut,
    ArtifactOut,
    AuditEventOut,
    CandidateCreate,
    CandidateCategoryUpdate,
    CandidateOut,
    ExperimentCreate,
    ExperimentOut,
    JobLinkCreate,
    JobLinkOut,
    MeasurementOut,
    MutationUpdate,
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberOut,
    ProjectMemberUpdate,
    ProjectOut,
    ProjectUpdate,
    SampleBatchCreate,
    SampleBatchOut,
    SequenceDifferenceOut,
    VersionComparisonOut,
    VersionCreate,
    VersionImportRequest,
    VersionLockDrafts,
    VersionOut,
    VersionUpdate,
)


router = APIRouter(prefix="/api/antibody-projects", tags=["antibody-projects"])
ARTIFACT_CATEGORIES = {"sequence", "structure", "experiment", "job", "report", "other"}


def _experiment_out(db: Session, experiment: ExperimentRecord) -> ExperimentOut:
    measurements = db.scalars(
        select(ExperimentMeasurement)
        .where(ExperimentMeasurement.experiment_id == experiment.id)
        .order_by(ExperimentMeasurement.metric_name, ExperimentMeasurement.replicate)
    ).all()
    payload = model_snapshot(experiment)
    payload["measurements"] = [
        MeasurementOut.model_validate(item) for item in measurements
    ]
    return ExperimentOut.model_validate(payload)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project_api(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = create_project(db, body, user)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("", response_model=list[ProjectOut])
def list_projects_api(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return [
        ProjectOut.model_validate(item)
        for item in visible_projects(db, user, include_archived=include_archived)
    ]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project_api(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ProjectOut.model_validate(project_access(db, project_id, user))


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project_api(
    project_id: str,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    project = update_project(db, project, body, user)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
def list_members_api(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    rows = db.execute(
        select(ProjectMember, User.username)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    ).all()
    return [
        ProjectMemberOut(
            id=member.id,
            user_id=member.user_id,
            username=username,
            role=member.role,
            created_at=member.created_at,
        )
        for member, username in rows
    ]


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_member_api(
    project_id: str,
    body: ProjectMemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.owner.value)
    member, target = add_project_member(db, project, body.username, body.role, user)
    db.commit()
    db.refresh(member)
    return ProjectMemberOut(
        id=member.id,
        user_id=member.user_id,
        username=target.username,
        role=member.role,
        created_at=member.created_at,
    )


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMemberOut)
def update_member_api(
    project_id: str,
    member_id: str,
    body: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.owner.value)
    member = db.get(ProjectMember, member_id)
    if not member or member.project_id != project.id:
        raise HTTPException(404, "项目成员不存在")
    if member.user_id == project.owner_id:
        raise HTTPException(409, "不能修改项目负责人的角色")
    before = model_snapshot(member)
    member.role = body.role
    target = db.get(User, member.user_id)
    add_audit(
        db,
        project_id=project.id,
        entity_type="project_member",
        entity_id=member.id,
        action="update",
        actor_id=user.id,
        before=before,
        after=model_snapshot(member),
    )
    db.commit()
    db.refresh(member)
    return ProjectMemberOut(
        id=member.id,
        user_id=member.user_id,
        username=target.username,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member_api(
    project_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.owner.value)
    member = db.get(ProjectMember, member_id)
    if not member or member.project_id != project.id:
        raise HTTPException(404, "项目成员不存在")
    if member.user_id == project.owner_id:
        raise HTTPException(409, "不能移除项目负责人")
    before = model_snapshot(member)
    db.delete(member)
    add_audit(
        db,
        project_id=project.id,
        entity_type="project_member",
        entity_id=member.id,
        action="delete",
        actor_id=user.id,
        before=before,
    )
    db.commit()


@router.post(
    "/{project_id}/candidates",
    response_model=CandidateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_candidate_api(
    project_id: str,
    body: CandidateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate, _wt = create_candidate_with_wt(db, project, body, user)
    db.commit()
    db.refresh(candidate)
    return CandidateOut.model_validate(candidate)


@router.get("/{project_id}/candidates", response_model=list[CandidateOut])
def list_candidates_api(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    rows = db.scalars(
        select(AntibodyCandidate)
        .where(AntibodyCandidate.project_id == project_id)
        .order_by(AntibodyCandidate.created_at)
    ).all()
    return [CandidateOut.model_validate(item) for item in rows]


@router.get("/{project_id}/candidates/{candidate_id}", response_model=CandidateOut)
def get_candidate_api(
    project_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    return CandidateOut.model_validate(get_candidate(db, project_id, candidate_id))


@router.patch(
    "/{project_id}/candidates/{candidate_id}/category",
    response_model=CandidateOut,
)
def set_candidate_category_api(
    project_id: str,
    candidate_id: str,
    body: CandidateCategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate = set_candidate_category(
        db,
        project,
        get_candidate(db, project_id, candidate_id),
        body.antibody_category,
        user,
    )
    db.commit()
    db.refresh(candidate)
    return CandidateOut.model_validate(candidate)


@router.post(
    "/{project_id}/candidates/{candidate_id}/versions",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_version_api(
    project_id: str,
    candidate_id: str,
    body: VersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate = get_candidate(db, project_id, candidate_id)
    version = create_version(db, project, candidate, body, user)
    db.commit()
    db.refresh(version)
    return version_out(db, version)


@router.post(
    "/{project_id}/candidates/{candidate_id}/versions/import",
    response_model=list[VersionOut],
    status_code=status.HTTP_201_CREATED,
)
def import_versions_api(
    project_id: str,
    candidate_id: str,
    body: VersionImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate = get_candidate(db, project_id, candidate_id)
    versions = import_versions(db, project, candidate, body, user)
    db.commit()
    return [version_out(db, item) for item in versions]


@router.post(
    "/{project_id}/candidates/{candidate_id}/versions/import-fasta",
    response_model=list[VersionOut],
    status_code=status.HTTP_201_CREATED,
)
def import_versions_fasta_api(
    project_id: str,
    candidate_id: str,
    parent_version_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate = get_candidate(db, project_id, candidate_id)
    versions = import_versions_from_fasta(
        db,
        project,
        candidate,
        parent_version_id,
        file.file.read(),
        file.filename,
        user,
    )
    db.commit()
    return [version_out(db, item) for item in versions]


@router.post(
    "/{project_id}/candidates/{candidate_id}/versions/import-xlsx",
    response_model=list[VersionOut],
    status_code=status.HTTP_201_CREATED,
)
def import_versions_xlsx_api(
    project_id: str,
    candidate_id: str,
    parent_version_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate = get_candidate(db, project_id, candidate_id)
    versions = import_versions_from_xlsx(
        db,
        project,
        candidate,
        parent_version_id,
        file.file.read(),
        file.filename,
        user,
    )
    db.commit()
    return [version_out(db, item) for item in versions]


@router.get(
    "/{project_id}/candidates/{candidate_id}/versions",
    response_model=list[VersionOut],
)
def list_versions_api(
    project_id: str,
    candidate_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    candidate = get_candidate(db, project_id, candidate_id)
    rows = db.scalars(
        select(AntibodyVersion)
        .where(AntibodyVersion.candidate_id == candidate.id)
        .order_by(AntibodyVersion.version_number)
    ).all()
    return [version_out(db, item) for item in rows]


@router.get("/{project_id}/versions/{version_id}", response_model=VersionOut)
def get_version_api(
    project_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    return version_out(db, get_version(db, project_id, version_id))


@router.patch("/{project_id}/versions/{version_id}", response_model=VersionOut)
def update_version_api(
    project_id: str,
    version_id: str,
    body: VersionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    version = update_draft_version(
        db, project, get_version(db, project_id, version_id), body, user
    )
    db.commit()
    db.refresh(version)
    return version_out(db, version)


@router.post("/{project_id}/versions/{version_id}/lock", response_model=VersionOut)
def lock_version_api(
    project_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    version = lock_version(
        db, project, get_version(db, project_id, version_id), user
    )
    db.commit()
    db.refresh(version)
    return version_out(db, version)


@router.post(
    "/{project_id}/candidates/{candidate_id}/versions/lock-drafts",
    response_model=list[VersionOut],
)
def lock_draft_versions_api(
    project_id: str,
    candidate_id: str,
    body: VersionLockDrafts,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate = get_candidate(db, project_id, candidate_id)
    versions = lock_draft_versions(db, project, candidate, body.round, user)
    db.commit()
    return [version_out(db, item) for item in versions]


@router.patch(
    "/{project_id}/versions/{version_id}/mutations/{mutation_id}",
    response_model=VersionOut,
)
def update_mutation_api(
    project_id: str,
    version_id: str,
    mutation_id: str,
    body: MutationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    version = get_version(db, project_id, version_id)
    if version.status != "draft":
        raise HTTPException(409, "只有草稿版本的突变说明可以修改")
    mutation = db.get(VersionMutation, mutation_id)
    if not mutation or mutation.version_id != version.id:
        raise HTTPException(404, "突变记录不存在")
    before = model_snapshot(mutation)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(mutation, field, value)
    add_audit(
        db,
        project_id=project.id,
        entity_type="version_mutation",
        entity_id=mutation.id,
        action="update",
        actor_id=user.id,
        before=before,
        after=model_snapshot(mutation),
    )
    db.commit()
    db.refresh(version)
    return version_out(db, version)


@router.get("/{project_id}/compare", response_model=VersionComparisonOut)
def compare_versions_api(
    project_id: str,
    base_version_id: str = Query(...),
    target_version_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    base = get_version(db, project_id, base_version_id)
    target = get_version(db, project_id, target_version_id)
    if base.candidate_id != target.candidate_id:
        raise HTTPException(400, "只能比较同一候选抗体的版本")
    base_out = version_out(db, base)
    target_out = version_out(db, target)
    base_chains = {item.chain_role: item.variable_sequence for item in base_out.chains}
    target_chains = {item.chain_role: item.variable_sequence for item in target_out.chains}
    differences = []
    for role in sorted(base_chains):
        if role not in target_chains:
            raise HTTPException(400, "两个版本的链角色不一致")
        differences.extend(
            SequenceDifferenceOut(chain_role=role, **item)
            for item in diff_sequences(base_chains[role], target_chains[role])
        )
    return VersionComparisonOut(
        base_version=base_out,
        target_version=target_out,
        differences=differences,
    )


@router.post(
    "/{project_id}/samples",
    response_model=SampleBatchOut,
    status_code=status.HTTP_201_CREATED,
)
def create_sample_api(
    project_id: str,
    body: SampleBatchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    sample = create_sample_batch(db, project, body, user)
    db.commit()
    db.refresh(sample)
    return SampleBatchOut.model_validate(sample)


@router.get("/{project_id}/samples", response_model=list[SampleBatchOut])
def list_samples_api(
    project_id: str,
    version_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    query = select(SampleBatch).join(
        AntibodyVersion, AntibodyVersion.id == SampleBatch.version_id
    ).join(AntibodyCandidate, AntibodyCandidate.id == AntibodyVersion.candidate_id)
    query = query.where(AntibodyCandidate.project_id == project_id)
    if version_id:
        get_version(db, project_id, version_id)
        query = query.where(SampleBatch.version_id == version_id)
    rows = db.scalars(query.order_by(SampleBatch.created_at.desc())).all()
    return [SampleBatchOut.model_validate(item) for item in rows]


@router.post(
    "/{project_id}/experiments",
    response_model=ExperimentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment_api(
    project_id: str,
    body: ExperimentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    experiment = create_experiment(db, project, body, user)
    db.commit()
    db.refresh(experiment)
    return _experiment_out(db, experiment)


@router.get("/{project_id}/experiments", response_model=list[ExperimentOut])
def list_experiments_api(
    project_id: str,
    version_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    query = select(ExperimentRecord).where(ExperimentRecord.project_id == project_id)
    if version_id:
        get_version(db, project_id, version_id)
        query = query.where(ExperimentRecord.version_id == version_id)
    rows = db.scalars(query.order_by(ExperimentRecord.created_at.desc())).all()
    return [_experiment_out(db, item) for item in rows]


@router.post(
    "/{project_id}/candidates/{candidate_id}/experiments/preview-affinity-xlsx",
    response_model=AffinityPreviewOut,
)
def preview_affinity_xlsx_api(
    project_id: str,
    candidate_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate = get_candidate(db, project_id, candidate_id)
    return preview_affinity_xlsx(db, project, candidate, file.file.read(), file.filename)


@router.post(
    "/{project_id}/candidates/{candidate_id}/experiments/import-affinity-xlsx",
    response_model=list[ExperimentOut],
    status_code=status.HTTP_201_CREATED,
)
def import_affinity_xlsx_api(
    project_id: str,
    candidate_id: str,
    body: AffinityImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    candidate = get_candidate(db, project_id, candidate_id)
    experiments = import_affinity_xlsx(db, project, candidate, body, user)
    db.commit()
    return [_experiment_out(db, item) for item in experiments]


@router.post(
    "/{project_id}/job-links",
    response_model=JobLinkOut,
    status_code=status.HTTP_201_CREATED,
)
def create_job_link_api(
    project_id: str,
    body: JobLinkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    link = create_job_link(db, project, body, user)
    db.commit()
    db.refresh(link)
    return JobLinkOut.model_validate(link)


@router.get("/{project_id}/job-links", response_model=list[JobLinkOut])
def list_job_links_api(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    rows = db.scalars(
        select(ProjectJobLink)
        .where(ProjectJobLink.project_id == project_id)
        .order_by(ProjectJobLink.created_at.desc())
    ).all()
    return [JobLinkOut.model_validate(item) for item in rows]


def _validate_artifact_links(
    db: Session,
    project_id: str,
    *,
    version_id: str | None,
    sample_batch_id: str | None,
    experiment_id: str | None,
    job_link_id: str | None,
) -> None:
    linked_versions: set[str] = set()
    if version_id:
        get_version(db, project_id, version_id)
        linked_versions.add(version_id)
    if sample_batch_id:
        sample = db.get(SampleBatch, sample_batch_id)
        if not sample:
            raise HTTPException(400, "样品批次不存在")
        get_version(db, project_id, sample.version_id)
        linked_versions.add(sample.version_id)
    if experiment_id:
        experiment = db.get(ExperimentRecord, experiment_id)
        if not experiment or experiment.project_id != project_id:
            raise HTTPException(400, "实验记录不存在")
        linked_versions.add(experiment.version_id)
    if job_link_id:
        link = db.get(ProjectJobLink, job_link_id)
        if not link or link.project_id != project_id:
            raise HTTPException(400, "任务关联不存在")
        linked_versions.add(link.version_id)
    if len(linked_versions) > 1:
        raise HTTPException(400, "附件关联的版本、样品、实验或任务不一致")


@router.post(
    "/{project_id}/artifacts",
    response_model=ArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_artifact_api(
    project_id: str,
    file: UploadFile = File(...),
    category: str = Form(default="other"),
    version_id: str | None = Form(default=None),
    sample_batch_id: str | None = Form(default=None),
    experiment_id: str | None = Form(default=None),
    job_link_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    if category not in ARTIFACT_CATEGORIES:
        raise HTTPException(400, "附件分类无效")
    _validate_artifact_links(
        db,
        project_id,
        version_id=version_id,
        sample_batch_id=sample_batch_id,
        experiment_id=experiment_id,
        job_link_id=job_link_id,
    )
    file_name = Path(file.filename or "attachment.bin").name
    artifact_id = str(uuid.uuid4())
    destination_dir = project_storage_dir(project_id) / category
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{artifact_id}_{file_name}"
    max_bytes = settings.antibody_project_max_upload_mb * 1024 * 1024
    size = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, "附件超过大小限制")
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(400, "附件不能为空")

    artifact = ProjectArtifact(
        id=artifact_id,
        project_id=project.id,
        version_id=version_id,
        sample_batch_id=sample_batch_id,
        experiment_id=experiment_id,
        job_link_id=job_link_id,
        category=category,
        file_name=file_name,
        storage_path=str(destination.relative_to(settings.antibody_projects_out_root)),
        sha256=sha256_file(destination),
        size_bytes=size,
        mime_type=file.content_type,
        uploaded_by=user.id,
    )
    db.add(artifact)
    db.flush()
    add_audit(
        db,
        project_id=project.id,
        entity_type="artifact",
        entity_id=artifact.id,
        action="create",
        actor_id=user.id,
        after=model_snapshot(artifact),
    )
    db.commit()
    db.refresh(artifact)
    return ArtifactOut.model_validate(artifact)


@router.get("/{project_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts_api(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    rows = db.scalars(
        select(ProjectArtifact)
        .where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.deleted_at.is_(None),
        )
        .order_by(ProjectArtifact.created_at.desc())
    ).all()
    return [ArtifactOut.model_validate(item) for item in rows]


@router.get("/{project_id}/artifacts/{artifact_id}/download")
def download_artifact_api(
    project_id: str,
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    artifact = db.get(ProjectArtifact, artifact_id)
    if (
        not artifact
        or artifact.project_id != project_id
        or artifact.deleted_at is not None
    ):
        raise HTTPException(404, "附件不存在")
    root = settings.antibody_projects_out_root.resolve()
    path = (root / artifact.storage_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "附件文件不存在")
    return FileResponse(path, filename=artifact.file_name, media_type=artifact.mime_type)


@router.delete(
    "/{project_id}/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_artifact_api(
    project_id: str,
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = project_access(db, project_id, user, ProjectRole.editor.value)
    artifact = db.get(ProjectArtifact, artifact_id)
    if (
        not artifact
        or artifact.project_id != project.id
        or artifact.deleted_at is not None
    ):
        raise HTTPException(404, "附件不存在")
    before = model_snapshot(artifact)
    artifact.deleted_at = datetime.now(timezone.utc)
    add_audit(
        db,
        project_id=project.id,
        entity_type="artifact",
        entity_id=artifact.id,
        action="delete",
        actor_id=user.id,
        before=before,
        after=model_snapshot(artifact),
    )
    db.commit()


@router.get("/{project_id}/audit-events", response_model=list[AuditEventOut])
def list_audit_events_api(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_access(db, project_id, user)
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.project_id == project_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [AuditEventOut.model_validate(item) for item in rows]
