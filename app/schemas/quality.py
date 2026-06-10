"""Schémas — Module qualité (non-conformités + CAPA), ISO 15189 §4.9/§4.10."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NCSource = Literal["qc", "critical", "maintenance", "manual", "other"]
NCSeverity = Literal["minor", "major", "critical"]
NCStatus = Literal["open", "analysis", "action", "verification", "closed"]
ActionType = Literal["corrective", "preventive"]
ActionStatus = Literal["planned", "in_progress", "done"]


# ── Non-conformité ──────────────────────────────────────────────────────────

class NonConformityCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    source: NCSource = "manual"
    severity: NCSeverity = "minor"
    linked_entity_type: str | None = Field(default=None, max_length=50)
    linked_entity_id: str | None = Field(default=None, max_length=50)
    due_date: dt.datetime | None = None
    model_config = ConfigDict(extra="forbid")


class NonConformityTransition(BaseModel):
    status: NCStatus
    root_cause: str | None = Field(default=None, max_length=5000)
    model_config = ConfigDict(extra="forbid")


class CorrectiveActionRead(BaseModel):
    id: int
    non_conformity_id: int
    action_type: str
    description: str
    responsible_id: int | None = None
    due_date: dt.datetime | None = None
    status: str
    effectiveness_checked: bool = False
    effectiveness_notes: str | None = None
    completed_at: dt.datetime | None = None
    created_at: dt.datetime
    model_config = ConfigDict(from_attributes=True)


class NonConformityRead(BaseModel):
    id: int
    title: str
    description: str | None = None
    source: str
    severity: str
    status: str
    linked_entity_type: str | None = None
    linked_entity_id: str | None = None
    detected_by_id: int | None = None
    detected_at: dt.datetime
    due_date: dt.datetime | None = None
    closed_at: dt.datetime | None = None
    root_cause: str | None = None
    created_at: dt.datetime
    actions: list[CorrectiveActionRead] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


# ── Action corrective / préventive ──────────────────────────────────────────

class CorrectiveActionCreate(BaseModel):
    action_type: ActionType = "corrective"
    description: str = Field(..., min_length=3, max_length=5000)
    responsible_id: int | None = None
    due_date: dt.datetime | None = None
    model_config = ConfigDict(extra="forbid")


class CorrectiveActionUpdate(BaseModel):
    status: ActionStatus | None = None
    effectiveness_checked: bool | None = None
    effectiveness_notes: str | None = Field(default=None, max_length=5000)
    model_config = ConfigDict(extra="forbid")
