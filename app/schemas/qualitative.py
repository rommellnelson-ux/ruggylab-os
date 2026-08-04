"""Schémas des résultats qualitatifs de paillasse (Flux 3).

Couvre la saisie de résultats non chiffrés — parasitologie, cytologie,
frottis — depuis le cockpit de microscopie. La donnée métier hétérogène est
portée par ``findings`` (sérialisé dans ``Result.data_points`` JSONB) ; le
discriminateur ``Result.result_type`` reste ``"qualitative"``.

Anti-fautes de frappe : ``density`` est un vocabulaire **fermé** (``Literal``),
et le frontend couple les noms d'organismes à des ``<datalist>`` cliniques.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Échelle de densité / rareté commune (parasitologie + cytologie).
# Fermée volontairement : tout autre libellé est rejeté (422).
DensityScale = Literal["Rares", "+", "++", "+++", "++++", "Présence", "Nombreux"]

# Catégories de paillasse qualitative prises en charge.
QualitativeCategory = Literal["parasitology", "cytology", "smear"]


class QualitativeObservation(BaseModel):
    """Une observation unitaire : un organisme/élément et sa densité."""

    organism: str = Field(..., min_length=1, max_length=120)
    density: DensityScale

    model_config = ConfigDict(extra="forbid")


class QualitativeFindings(BaseModel):
    """Corps métier du résultat qualitatif (sérialisé en JSONB)."""

    is_negative: bool = Field(
        ...,
        description="Vrai = RAS / absence (aucune observation attendue).",
    )
    observations: list[QualitativeObservation] = Field(default_factory=list, max_length=50)
    comment: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _coherence(self) -> QualitativeFindings:
        # Cohérence : un résultat positif doit porter au moins une observation ;
        # un résultat négatif n'en porte aucune.
        if self.is_negative and self.observations:
            raise ValueError("Résultat négatif (RAS) : aucune observation ne doit être fournie.")
        if not self.is_negative and not self.observations:
            raise ValueError("Résultat positif : au moins une observation est requise.")
        return self


class QualitativeResultSubmission(BaseModel):
    """Payload envoyé par le cockpit de microscopie à /results/qualitative."""

    sample_barcode: str = Field(..., min_length=1, max_length=100)
    category: QualitativeCategory
    result_type: Literal["qualitative"] = "qualitative"
    exam_code: str | None = Field(default=None, max_length=50)
    # Réutilise la clé image du composant de capture microscope existant
    # (/imaging/capture-microscope renvoie ce chemin réservé côté serveur).
    image_url: str | None = Field(default=None, max_length=255)
    findings: QualitativeFindings

    model_config = ConfigDict(extra="forbid")


class QualitativeResultResponse(BaseModel):
    status: str
    message: str
    result_id: int
    is_critical: bool
    is_validated: bool
    image_url: str | None = None
