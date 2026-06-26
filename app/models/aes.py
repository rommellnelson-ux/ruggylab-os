"""Registre des Accidents d'Exposition au Sang (AES) — sécurité du personnel.

Obligation de traçabilité des expositions (piqûre, coupure, projection) :
déclaration, mesures d'urgence, statut sérologique de la source, suivi 6 mois.
Module isolé (fichier dédié) pour ne pas dépendre du reste des modèles.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.utils.datetime_utils import utcnow_naive


class AesIncident(Base):
    __tablename__ = "aes_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Agent exposé (utilisateur si connu) + libellé libre de secours.
    agent_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    agent_label: Mapped[str | None] = mapped_column(String(150))
    declared_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str | None] = mapped_column(String(150))
    # piqure | coupure | projection_muqueuse | projection_peau_lesee | autre
    exposure_type: Mapped[str] = mapped_column(String(40), nullable=False, default="piqure")
    circumstances: Mapped[str] = mapped_column(Text, nullable=False)
    immediate_measures: Mapped[str | None] = mapped_column(Text)

    # Source (patient) si connue + statut sérologique (VIH/VHB/VHC).
    source_label: Mapped[str | None] = mapped_column(String(150))
    source_serology: Mapped[str | None] = mapped_column(String(120))

    # declared -> in_followup -> closed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="declared", index=True)
    followup_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
