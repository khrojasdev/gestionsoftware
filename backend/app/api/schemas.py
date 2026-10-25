"""Pydantic contracts exposed by the public Trazo API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    ChangePriority,
    ChangeStatus,
    ChangeType,
    GanttElementType,
    KpiScope,
    ProjectStatus,
    ResourceType,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class ProjectCreate(ApiModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    status: ProjectStatus = ProjectStatus.DRAFT
    planned_start: date | None = None
    committed_finish: date | None = None
    cutoff_date: date | None = None
    budget: Decimal = Field(default=Decimal("0"), ge=0)
    contingency_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    working_hours_per_day: Decimal = Field(default=Decimal("8"), gt=0)
    working_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5], min_length=1)


class ProjectUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    status: ProjectStatus | None = None
    planned_start: date | None = None
    committed_finish: date | None = None
    cutoff_date: date | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    contingency_pct: Decimal | None = Field(default=None, ge=0, le=100)
    working_hours_per_day: Decimal | None = Field(default=None, gt=0)
    working_days: list[int] | None = Field(default=None, min_length=1)


class GanttCreate(ApiModel):
    external_id: str = Field(min_length=1, max_length=80)
    element_type: GanttElementType
    name: str = Field(min_length=1, max_length=300)
    parent_external_id: str | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    duration_days: int | None = Field(default=None, ge=0)
    predecessors: str | None = None
    progress_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    planned_cost: Decimal = Field(default=Decimal("0"), ge=0)
    effort_hours: Decimal | None = Field(default=None, ge=0)


class GanttUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    planned_start: date | None = None
    planned_finish: date | None = None
    duration_days: int | None = Field(default=None, ge=0)
    progress_pct: Decimal | None = Field(default=None, ge=0, le=100)
    planned_cost: Decimal | None = Field(default=None, ge=0)
    actual_start: date | None = None
    actual_finish: date | None = None


class ProgressCreate(ApiModel):
    cutoff_at: datetime
    progress_pct: Decimal = Field(ge=0, le=100)
    actual_start: date | None = None
    actual_finish: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class ResourceCreate(ApiModel):
    external_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    resource_type: ResourceType
    role: str | None = Field(default=None, max_length=160)
    rate: Decimal = Field(default=Decimal("0"), ge=0)
    unit: str | None = Field(default=None, max_length=40)
    capacity_hours_per_day: Decimal | None = Field(default=None, ge=0)


class AssignmentCreate(ApiModel):
    element_id: uuid.UUID
    resource_id: uuid.UUID
    planned_hours: Decimal = Field(default=Decimal("0"), ge=0)
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    hours_per_day: Decimal = Field(default=Decimal("0"), ge=0)
    rate_override: Decimal | None = Field(default=None, ge=0)


class KpiCreate(ApiModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    formula: str = Field(min_length=1, max_length=2000)
    scope: KpiScope
    element_id: uuid.UUID | None = None
    target: Decimal | None = None
    green_threshold: Decimal | None = None
    yellow_threshold: Decimal | None = None
    red_threshold: Decimal | None = None
    frequency: str = Field(default="CORTE", max_length=40)
    alert_rule: str | None = Field(default=None, max_length=1000)


class KpiUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    formula: str | None = Field(default=None, min_length=1, max_length=2000)
    scope: KpiScope | None = None
    element_id: uuid.UUID | None = None
    target: Decimal | None = None
    green_threshold: Decimal | None = None
    yellow_threshold: Decimal | None = None
    red_threshold: Decimal | None = None
    frequency: str | None = Field(default=None, max_length=40)
    alert_rule: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class KpiVariableCreate(ApiModel):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    description: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=300)
    calculation_method: str = Field(min_length=1, max_length=1000)
    data_type: str = Field(default="DECIMAL", min_length=1, max_length=30)


class ChangeCreate(ApiModel):
    code: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=4000)
    change_type: ChangeType
    priority: ChangePriority = ChangePriority.MEDIUM


class ChangeTransitionCreate(ApiModel):
    status: ChangeStatus
    comment: str | None = Field(default=None, max_length=2000)
    to_stage_id: uuid.UUID | None = None


class ImportRequest(ApiModel):
    source_path: str = Field(min_length=1, max_length=1000)


class DataResponse(ApiModel):
    data: Any


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(ApiModel):
    error: ErrorBody
