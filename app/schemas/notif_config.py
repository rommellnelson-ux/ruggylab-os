"""Schemas — Configuration des alertes critiques non-acquittées."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NotifConfigCreate(BaseModel):
    webhook_url: str | None = Field(None, max_length=500)
    email: str | None = Field(None, max_length=200)
    delay_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        description="Délai (min) avant envoi d'une alerte pour un résultat critique non-acquitté",
    )

    @model_validator(mode="after")
    def at_least_one_channel(self) -> Self:
        if not self.webhook_url and not self.email:
            raise ValueError(
                "Au moins un canal de notification (webhook_url ou email) doit être défini."
            )
        return self


class NotifConfigRead(NotifConfigCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class PendingCriticalEntry(BaseModel):
    result_id: int
    sample_id: int
    analysis_date: str | None
    elapsed_minutes: int
    overdue: bool


class NotifyResult(BaseModel):
    notified: int
    pending: int
