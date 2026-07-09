import datetime as dt
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Statuts que l'utilisateur peut poser via l'API (create/update) — miroir du
# sélecteur du cockpit. Source de vérité du chemin d'écriture.
ALLOWED_SAMPLE_STATUSES = {"Recu", "En cours", "Termine", "Annule"}
# Statuts posés uniquement par des services internes (import registre papier,
# seed de démonstration) via l'ORM, hors validation d'entrée. Ils sont
# légitimes en base ; la lecture doit les tolérer sans jamais renvoyer 500.
SYSTEM_SAMPLE_STATUSES = {"Importé (historique)", "Démo"}
# Aspect pré-analytique : qualité de l'échantillon (≠ statut workflow).
ALLOWED_SAMPLE_ASPECTS = {
    "conforme",
    "hemolyse",
    "icterique",
    "lipemique",
    "coagule",
    "insuffisant",
}


def _validate_aspect(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    if value not in ALLOWED_SAMPLE_ASPECTS:
        raise ValueError("aspect is not supported")
    return value


class SampleBase(BaseModel):
    barcode: str = Field(..., min_length=1, max_length=100)
    patient_id: int | None = Field(default=None, ge=1)
    collection_date: dt.datetime | None = None
    received_date: dt.datetime | None = None
    status: str | None = Field(default=None, max_length=50)
    aspect: str | None = Field(default=None, max_length=20)
    # N° labo lisible : généré côté serveur si absent (séquence annuelle).
    lab_number: str | None = Field(default=None, max_length=20)
    collected_by_label: str | None = Field(default=None, max_length=150)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in ALLOWED_SAMPLE_STATUSES:
            raise ValueError("status is not supported")
        return value

    @field_validator("aspect")
    @classmethod
    def validate_aspect(cls, value: str | None) -> str | None:
        return _validate_aspect(value)

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        now = dt.datetime.now(dt.UTC)
        collection_date = _as_aware_utc(self.collection_date)
        received_date = _as_aware_utc(self.received_date)
        if collection_date and collection_date > now:
            raise ValueError("collection_date cannot be in the future")
        if received_date and received_date > now:
            raise ValueError("received_date cannot be in the future")
        if collection_date and received_date and received_date < collection_date:
            raise ValueError("received_date cannot be before collection_date")
        return self


def _as_aware_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


class SampleCreate(SampleBase):
    model_config = ConfigDict(extra="forbid")


class SampleUpdate(BaseModel):
    """Partial update — statut et/ou aspect."""

    status: str | None = None
    aspect: str | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in ALLOWED_SAMPLE_STATUSES:
            raise ValueError("status is not supported")
        return value

    @field_validator("aspect")
    @classmethod
    def validate_aspect(cls, value: str | None) -> str | None:
        return _validate_aspect(value)


class SampleRead(SampleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        # Défense en profondeur : la lecture ne valide PAS le statut contre la
        # liste blanche. Un statut inattendu (import registre, seed, migration)
        # ne doit jamais faire échouer la sérialisation de toute la collection
        # — une seule ligne « empoisonnait » GET /samples et /results/cockpit.
        # La contrainte stricte reste sur l'écriture (SampleCreate/SampleUpdate).
        return value
