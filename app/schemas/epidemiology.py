"""Schémas Pydantic pour le tableau de bord épidémiologique."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field, model_validator


class EpidemiologyRequest(BaseModel):
    """Corps de la requête POST /epidemiology/dashboard."""

    start_date: datetime.date | None = Field(
        default=None,
        description="Date de début de la période (défaut : 30 derniers jours)",
    )
    end_date: datetime.date | None = Field(
        default=None,
        description="Date de fin de la période (défaut : aujourd'hui)",
    )
    facility_ids: list[int] | None = Field(
        default=None,
        description="Filtre optionnel par identifiant d'équipement (proxy pour l'établissement)",
    )
    parameters: list[str] | None = Field(
        default=None,
        description="Paramètres biologiques à analyser, ex. ['WBC', 'HGB']. Tous si None.",
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> EpidemiologyRequest:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date doit être antérieure ou égale à end_date.")
        return self


class ParameterStats(BaseModel):
    """Statistiques agrégées pour un paramètre biologique donné."""

    parameter: str = Field(description="Nom du paramètre, ex. 'WBC'")
    total_results: int = Field(description="Nombre total de mesures pour ce paramètre")
    critical_count: int = Field(description="Nombre de résultats CRITICAL_LOW ou CRITICAL_HIGH")
    critical_rate: float = Field(description="Taux de critiques (critical_count / total_results)")
    mean_value: float | None = Field(default=None, description="Valeur moyenne")
    min_value: float | None = Field(default=None, description="Valeur minimale")
    max_value: float | None = Field(default=None, description="Valeur maximale")


class FacilityStats(BaseModel):
    """Statistiques agrégées par établissement (représenté par l'équipement)."""

    facility_id: int | None = Field(default=None, description="ID de l'équipement / établissement")
    facility_name: str | None = Field(
        default=None, description="Nom de l'équipement / établissement"
    )
    total_results: int = Field(description="Nombre total de résultats pour cet établissement")
    critical_count: int = Field(description="Nombre de résultats critiques")
    critical_rate: float = Field(description="Taux de résultats critiques")


class EpidemiologyDashboard(BaseModel):
    """Réponse complète du tableau de bord épidémiologique."""

    period_start: datetime.date = Field(description="Début de la période analysée")
    period_end: datetime.date = Field(description="Fin de la période analysée")
    total_results: int = Field(description="Nombre total de résultats dans la période")
    total_critical: int = Field(description="Nombre total de résultats critiques")
    overall_critical_rate: float = Field(description="Taux global de résultats critiques")
    parameter_stats: list[ParameterStats] = Field(
        description="Statistiques par paramètre, triées par taux de critiques décroissant"
    )
    facility_stats: list[FacilityStats] = Field(
        description="Statistiques par établissement, triées par nombre de critiques décroissant"
    )
    daily_critical_trend: list[dict] = Field(
        description="Tendance journalière des critiques, ex. [{'date': '2026-05-01', 'count': 3}]"
    )
