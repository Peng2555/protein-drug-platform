"""项目访问控制与审计辅助。"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from app.core.models import User
from app.modules.antibody_projects.models import (
    AntibodyProject,
    AuditEvent,
    ProjectMember,
    ProjectRole,
    ProjectStatus,
)


ROLE_LEVEL = {
    ProjectRole.viewer.value: 1,
    ProjectRole.editor.value: 2,
    ProjectRole.owner.value: 3,
}


def visible_projects(
    db: Session,
    user: User,
    *,
    include_archived: bool = False,
) -> list[AntibodyProject]:
    if user.is_admin:
        query = select(AntibodyProject)
    else:
        member_projects = select(ProjectMember.project_id).where(
            ProjectMember.user_id == user.id
        )
        query = select(AntibodyProject).where(
            or_(
                AntibodyProject.owner_id == user.id,
                AntibodyProject.id.in_(member_projects),
            )
        )
    if not include_archived:
        query = query.where(AntibodyProject.status != ProjectStatus.archived.value)
    return list(db.scalars(query.order_by(AntibodyProject.updated_at.desc())).all())


def project_access(
    db: Session,
    project_id: str,
    user: User,
    minimum_role: str = ProjectRole.viewer.value,
) -> AntibodyProject:
    project = db.get(AntibodyProject, project_id)
    if not project:
        raise HTTPException(404, "抗体项目不存在")

    if user.is_admin or project.owner_id == user.id:
        actual_role = ProjectRole.owner.value
    else:
        member = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
            )
        )
        if not member:
            raise HTTPException(404, "抗体项目不存在")
        actual_role = member.role

    if ROLE_LEVEL[actual_role] < ROLE_LEVEL[minimum_role]:
        raise HTTPException(403, "当前项目权限不足")
    return project


def model_snapshot(instance) -> dict:
    """把 SQLAlchemy 行转换成可写入 JSON 的审计快照。"""
    snapshot = {}
    for column in sqlalchemy_inspect(instance).mapper.column_attrs:
        value = getattr(instance, column.key)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        snapshot[column.key] = value
    return snapshot


def add_audit(
    db: Session,
    *,
    project_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            before_json=before,
            after_json=after,
        )
    )
