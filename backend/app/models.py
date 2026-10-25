"""Relational model for the Trazo planning and change-control domain.

The model deliberately keeps planning, actuals, baselines, KPI history and
change-control history separate.  This prevents mutable operational values
from changing an approved baseline or a historical KPI value.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base shared by the application and Alembic."""

    metadata = sa.MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class ResourceType(StrEnum):
    HUMAN = "HUMANO"
    EQUIPMENT = "EQUIPAMIENTO"
    INFRASTRUCTURE_LICENSE = "INFRAESTRUCTURA_LICENCIA"
    EXTERNAL_SERVICE = "SERVICIO_EXTERNO"


class ProjectStatus(StrEnum):
    DRAFT = "BORRADOR"
    ACTIVE = "ACTIVO"
    CLOSED = "CERRADO"
    ARCHIVED = "ARCHIVADO"


class CalendarDayType(StrEnum):
    HOLIDAY = "FERIADO"
    NON_WORKING = "NO_LABORABLE"
    RESOURCE_EXCEPTION = "EXCEPCION_RECURSO"


class GanttElementType(StrEnum):
    STAGE = "ETAPA"
    ACTIVITY = "ACTIVIDAD"
    SUBACTIVITY = "SUBACTIVIDAD"
    MILESTONE = "HITO"


class DependencyType(StrEnum):
    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"


class BaselineStatus(StrEnum):
    ACTIVE = "VIGENTE"
    SUPERSEDED = "REEMPLAZADA"


class KpiScope(StrEnum):
    PROJECT = "PROYECTO"
    STAGE = "ETAPA"
    MILESTONE = "HITO"


class ChangeType(StrEnum):
    SCOPE = "ALCANCE"
    SCHEDULE = "PLAZO"
    COST = "COSTO"
    RESOURCE = "RECURSOS"


class ChangePriority(StrEnum):
    LOW = "BAJA"
    MEDIUM = "MEDIA"
    HIGH = "ALTA"
    CRITICAL = "CRITICA"


class ChangeStatus(StrEnum):
    OPEN = "ABIERTA"
    APPROVED = "APROBADA"
    REJECTED = "RECHAZADA"
    CANCELLED = "CANCELADA"
    CLOSED = "CERRADA"


class ChangeStageStatus(StrEnum):
    PENDING = "PENDIENTE"
    ACTIVE = "ACTIVA"
    COMPLETED = "COMPLETADA"
    SKIPPED = "OMITIDA"


class CriterionStatus(StrEnum):
    PENDING = "PENDIENTE"
    MET = "CUMPLIDO"
    NOT_MET = "NO_CUMPLIDO"


def enum_type(enum_cls: type[StrEnum], name: str) -> sa.Enum:
    """Use stable Spanish enum values rather than Python member names."""

    return sa.Enum(
        enum_cls,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        native_enum=True,
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(sa.String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", back_populates="users")


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500))

    users: Mapped[list[User]] = relationship(secondary="user_roles", back_populates="roles")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(sa.String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    client: Mapped[str | None] = mapped_column(sa.String(200))
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ProjectStatus] = mapped_column(
        enum_type(ProjectStatus, "project_status"), nullable=False, default=ProjectStatus.DRAFT
    )
    planned_start: Mapped[date | None] = mapped_column(sa.Date)
    committed_finish: Mapped[date | None] = mapped_column(sa.Date)
    cutoff_date: Mapped[date | None] = mapped_column(sa.Date)
    budget: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False, default=0)
    contingency_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, default=0
    )
    working_hours_per_day: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), nullable=False, default=8
    )
    working_days: Mapped[list[int]] = mapped_column(
        ARRAY(sa.SmallInteger), nullable=False, default=lambda: [1, 2, 3, 4, 5]
    )


class Resource(TimestampMixin, Base):
    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    resource_type: Mapped[ResourceType] = mapped_column(
        enum_type(ResourceType, "resource_type"), nullable=False
    )
    role: Mapped[str | None] = mapped_column(sa.String(160))
    rate: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False, default=0)
    unit: Mapped[str | None] = mapped_column(sa.String(40))
    capacity_hours_per_day: Mapped[Decimal | None] = mapped_column(sa.Numeric(8, 2))

    __table_args__ = (
        sa.UniqueConstraint("project_id", "external_id"),
        sa.UniqueConstraint("project_id", "id", name="uq_resources_project_id"),
        sa.CheckConstraint("rate >= 0", name="resource_rate_nonnegative"),
        sa.CheckConstraint(
            "capacity_hours_per_day IS NULL OR capacity_hours_per_day >= 0",
            name="resource_capacity_nonnegative",
        ),
        sa.Index("ix_resources_project_type", "project_id", "resource_type"),
    )


class CalendarEntry(Base):
    __tablename__ = "calendar_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    calendar_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    day_type: Mapped[CalendarDayType] = mapped_column(
        enum_type(CalendarDayType, "calendar_day_type"), nullable=False
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("resources.id", ondelete="CASCADE")
    )
    description: Mapped[str | None] = mapped_column(sa.String(300))

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ("project_id", "resource_id"),
            ("resources.project_id", "resources.id"),
            name="fk_calendar_entries_project_resource",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("project_id", "calendar_date", "resource_id"),
        sa.Index("ix_calendar_entries_lookup", "project_id", "calendar_date"),
    )


class GanttElement(TimestampMixin, Base):
    __tablename__ = "gantt_elements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    element_type: Mapped[GanttElementType] = mapped_column(
        enum_type(GanttElementType, "gantt_element_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="RESTRICT")
    )
    planned_start: Mapped[date | None] = mapped_column(sa.Date)
    planned_finish: Mapped[date | None] = mapped_column(sa.Date)
    duration_days: Mapped[int | None] = mapped_column(sa.Integer)
    actual_start: Mapped[date | None] = mapped_column(sa.Date)
    actual_finish: Mapped[date | None] = mapped_column(sa.Date)
    progress_pct: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False, default=0)
    planned_cost: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False, default=0)
    actual_cost: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False, default=0)
    effort_hours: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    total_slack_days: Mapped[int | None] = mapped_column(sa.Integer)
    free_slack_days: Mapped[int | None] = mapped_column(sa.Integer)
    is_critical: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    __table_args__ = (
        sa.UniqueConstraint("project_id", "external_id"),
        sa.UniqueConstraint("project_id", "id", name="uq_gantt_elements_project_id"),
        sa.ForeignKeyConstraint(
            ("project_id", "parent_id"),
            ("gantt_elements.project_id", "gantt_elements.id"),
            name="fk_gantt_elements_project_parent",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("duration_days IS NULL OR duration_days >= 0", name="duration_nonnegative"),
        sa.CheckConstraint("progress_pct BETWEEN 0 AND 100", name="progress_range"),
        sa.CheckConstraint("planned_cost >= 0 AND actual_cost >= 0", name="costs_nonnegative"),
        sa.Index("ix_gantt_elements_project_parent", "project_id", "parent_id"),
    )


class Dependency(Base):
    __tablename__ = "dependencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    predecessor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE"), nullable=False
    )
    successor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE"), nullable=False
    )
    dependency_type: Mapped[DependencyType] = mapped_column(
        enum_type(DependencyType, "dependency_type"), nullable=False, default=DependencyType.FS
    )
    lag_days: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ("project_id", "predecessor_id"),
            ("gantt_elements.project_id", "gantt_elements.id"),
            name="fk_dependencies_project_predecessor",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("project_id", "successor_id"),
            ("gantt_elements.project_id", "gantt_elements.id"),
            name="fk_dependencies_project_successor",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("predecessor_id", "successor_id"),
        sa.CheckConstraint("predecessor_id <> successor_id", name="no_self_dependency"),
        sa.Index("ix_dependencies_successor", "successor_id"),
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False
    )
    planned_hours: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), nullable=False, default=0)
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), nullable=False, default=0)
    hours_per_day: Mapped[Decimal] = mapped_column(sa.Numeric(8, 2), nullable=False, default=0)
    rate_override: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2))

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ("project_id", "element_id"),
            ("gantt_elements.project_id", "gantt_elements.id"),
            name="fk_assignments_project_element",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("project_id", "resource_id"),
            ("resources.project_id", "resources.id"),
            name="fk_assignments_project_resource",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("element_id", "resource_id"),
        sa.CheckConstraint("planned_hours >= 0 AND quantity >= 0 AND hours_per_day >= 0", name="assignment_values_nonnegative"),
        sa.CheckConstraint("rate_override IS NULL OR rate_override >= 0", name="override_nonnegative"),
        sa.Index("ix_assignments_resource", "resource_id"),
    )


class ProgressRecord(Base):
    __tablename__ = "progress_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE"), nullable=False
    )
    cutoff_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    progress_pct: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False)
    actual_start: Mapped[date | None] = mapped_column(sa.Date)
    actual_finish: Mapped[date | None] = mapped_column(sa.Date)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000))

    __table_args__ = (
        sa.UniqueConstraint("element_id", "cutoff_at"),
        sa.CheckConstraint("progress_pct BETWEEN 0 AND 100", name="progress_record_range"),
    )


class ActualCost(Base):
    __tablename__ = "actual_costs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (sa.CheckConstraint("amount >= 0", name="actual_amount_nonnegative"),)


class Baseline(TimestampMixin, Base):
    __tablename__ = "baselines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    status: Mapped[BaselineStatus] = mapped_column(
        enum_type(BaselineStatus, "baseline_status"), nullable=False, default=BaselineStatus.ACTIVE
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.UniqueConstraint("project_id", "version"),
        sa.Index(
            "uq_baselines_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=sa.text("status = 'VIGENTE'"),
        ),
    )


class BaselineElement(Base):
    __tablename__ = "baseline_elements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    baseline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("baselines.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    external_id: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    parent_external_id: Mapped[str | None] = mapped_column(sa.String(80))
    element_type: Mapped[GanttElementType] = mapped_column(
        enum_type(GanttElementType, "baseline_element_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    planned_start: Mapped[date | None] = mapped_column(sa.Date)
    planned_finish: Mapped[date | None] = mapped_column(sa.Date)
    duration_days: Mapped[int | None] = mapped_column(sa.Integer)
    planned_cost: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False, default=0)

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ("project_id", "element_id"),
            ("gantt_elements.project_id", "gantt_elements.id"),
            name="fk_baseline_elements_project_element",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("baseline_id", "external_id"),
    )


class Milestone(Base):
    __tablename__ = "milestones"

    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE"), primary_key=True
    )
    acceptance_status: Mapped[CriterionStatus] = mapped_column(
        enum_type(CriterionStatus, "milestone_acceptance_status"),
        nullable=False,
        default=CriterionStatus.PENDING,
    )


class AcceptanceCriterion(Base):
    __tablename__ = "acceptance_criteria"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("milestones.element_id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    description: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    verification_method: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[CriterionStatus] = mapped_column(
        enum_type(CriterionStatus, "criterion_status"), nullable=False, default=CriterionStatus.PENDING
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (sa.UniqueConstraint("milestone_id", "external_id"),)


class MilestoneTask(Base):
    __tablename__ = "milestone_tasks"

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("milestones.element_id", ondelete="CASCADE"), primary_key=True
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE"), primary_key=True
    )


class Kpi(Base):
    __tablename__ = "kpis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    formula: Mapped[str] = mapped_column(sa.String(2000), nullable=False)
    scope: Mapped[KpiScope] = mapped_column(enum_type(KpiScope, "kpi_scope"), nullable=False)
    element_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE")
    )
    target: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6))
    green_threshold: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6))
    yellow_threshold: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6))
    red_threshold: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 6))
    frequency: Mapped[str] = mapped_column(sa.String(40), nullable=False, default="CORTE")
    alert_rule: Mapped[str | None] = mapped_column(sa.String(1000))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ("project_id", "element_id"),
            ("gantt_elements.project_id", "gantt_elements.id"),
            name="fk_kpis_project_element",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("project_id", "code"),
    )


class KpiVariable(Base):
    __tablename__ = "kpi_variables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    description: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    calculation_method: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    data_type: Mapped[str] = mapped_column(sa.String(30), nullable=False, default="DECIMAL")

    __table_args__ = (sa.UniqueConstraint("project_id", "code"),)


class Dashboard(TimestampMixin, Base):
    """Persisted dashboard definition and its selected KPI codes."""

    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    dashboard_type: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    kpi_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (sa.UniqueConstraint("project_id", "external_id"),)


class KpiFormulaVersion(Base):
    __tablename__ = "kpi_formula_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("kpis.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    formula: Mapped[str] = mapped_column(sa.String(2000), nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    changed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utc_now, nullable=False)
    previous_formula: Mapped[str | None] = mapped_column(sa.String(2000))

    __table_args__ = (sa.UniqueConstraint("kpi_id", "version"),)


class KpiValue(Base):
    __tablename__ = "kpi_values"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("kpis.id", ondelete="CASCADE"), nullable=False
    )
    cutoff_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    element_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("gantt_elements.id", ondelete="CASCADE")
    )
    value: Mapped[Decimal | None] = mapped_column(sa.Numeric(24, 8))
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (sa.UniqueConstraint("kpi_id", "cutoff_at", "element_id"),)


class ChangeStage(Base):
    __tablename__ = "change_stages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    sla_hours: Mapped[int | None] = mapped_column(sa.Integer)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)

    __table_args__ = (sa.UniqueConstraint("project_id", "sequence"),)


class ChangeRequest(TimestampMixin, Base):
    __tablename__ = "change_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    description: Mapped[str] = mapped_column(sa.String(4000), nullable=False)
    change_type: Mapped[ChangeType] = mapped_column(
        enum_type(ChangeType, "change_type"), nullable=False
    )
    priority: Mapped[ChangePriority] = mapped_column(
        enum_type(ChangePriority, "change_priority"), nullable=False, default=ChangePriority.MEDIUM
    )
    status: Mapped[ChangeStatus] = mapped_column(
        enum_type(ChangeStatus, "change_status"), nullable=False, default=ChangeStatus.OPEN
    )
    requester_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    current_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("change_stages.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (sa.UniqueConstraint("project_id", "code"),)


class ChangeRequestStage(Base):
    __tablename__ = "change_request_stages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("change_stages.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ChangeStageStatus] = mapped_column(
        enum_type(ChangeStageStatus, "change_stage_status"), nullable=False, default=ChangeStageStatus.PENDING
    )
    entered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    exited_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(sa.String(2000))

    __table_args__ = (sa.UniqueConstraint("request_id", "stage_id"),)


class ChangeTransition(Base):
    __tablename__ = "change_transitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("change_stages.id", ondelete="RESTRICT")
    )
    to_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("change_stages.id", ondelete="RESTRICT")
    )
    from_status: Mapped[ChangeStatus | None] = mapped_column(enum_type(ChangeStatus, "transition_from_status"))
    to_status: Mapped[ChangeStatus] = mapped_column(enum_type(ChangeStatus, "transition_to_status"), nullable=False)
    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utc_now, nullable=False)
    comment: Mapped[str | None] = mapped_column(sa.String(2000))


class ChangeImpact(Base):
    __tablename__ = "change_impacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False
    )
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("baselines.id", ondelete="RESTRICT")
    )
    simulated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utc_now, nullable=False)
    proposed_project_finish: Mapped[date | None] = mapped_column(sa.Date)
    delta_schedule_days: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    delta_cost: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False, default=0)
    delta_contingency: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False, default=0)
    affected_elements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    resource_effect: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(sa.String(4000))


class Evidence(Base):
    __tablename__ = "evidences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("change_requests.id", ondelete="CASCADE")
    )
    criterion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("acceptance_criteria.id", ondelete="CASCADE")
    )
    file_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(sa.String(150))
    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        sa.CheckConstraint(
            "(change_request_id IS NOT NULL) <> (criterion_id IS NOT NULL)",
            name="evidence_has_one_owner",
        ),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="evidence_size_nonnegative"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (sa.Index("ix_audit_logs_entity", "entity_type", "entity_id"),)
