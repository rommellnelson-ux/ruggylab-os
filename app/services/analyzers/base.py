"""Abstraction des parseurs d'automates.

Contrat commun à tous les parseurs : une trame brute (str) entre, un
``AnalyzerResultBase`` normalisé sort. Le listener TCP ne parse rien
(capture aveugle vers Redis, cf. ``raw_tcp_listener``) ; c'est un worker de
dépilage qui, plus tard, rejouera les trames ``raw_analyzer_frames`` à
travers le parseur adapté au modèle d'automate.

Les implémentations concrètes (une par famille d'automate) vivent dans des
modules dédiés — ``dymind_hematology``, ``dymind_biochemistry``,
``anbio_immuno`` — et sont fabriquées via ``factory.AnalyzerParserFactory``.
Toutes sont des brouillons non implémentés tant que les manuels d'interfaçage
constructeur (HL7 ou ASTM ?) ne sont pas disponibles.
"""

from __future__ import annotations

import abc
import datetime as dt

from pydantic import BaseModel, Field


class AnalyzerResultBase(BaseModel):
    """Résultat normalisé produit par un parseur d'automate.

    C'est le pivot entre le monde « trames » (HL7, ASTM…) et le monde
    métier (rattachement échantillon / patient, validation médicale).
    """

    analyzer_model: str
    protocol: str = "unknown"  # "hl7" | "astm" | "unknown"
    sample_barcode: str | None = None
    patient_ipp: str | None = None
    message_control_id: str | None = None
    equipment_serial: str | None = None
    measured_at: dt.datetime | None = None
    # Paramètres mesurés, clé = code canonique RuggyLab (ex: "WBC", "HGB").
    parameters: dict[str, float] = Field(default_factory=dict)
    # Drapeaux qualité remontés par l'automate (ex: {"WBC": "H"}).
    flags: dict[str, str] = Field(default_factory=dict)
    # Empreinte de la trame d'origine, pour tracer le résultat jusqu'au brut.
    raw_sha256: str | None = None


class BaseAnalyzerParser(abc.ABC):
    """Contrat d'un parseur de trames automate.

    Les implémentations doivent être *pures* (pas d'accès BDD/Redis) : le
    rattachement métier reste dans la couche d'ingestion, ce qui permet de
    rejouer une trame archivée sans effet de bord.
    """

    #: Nom commercial du modèle, tel qu'enregistré dans Equipment.name.
    analyzer_model: str = "unknown"
    #: Protocole attendu ("hl7", "astm", "unknown" tant que non confirmé).
    protocol: str = "unknown"

    @abc.abstractmethod
    def parse(self, raw_frame: str) -> AnalyzerResultBase:
        """Transforme une trame brute en résultat normalisé.

        Lève ``ValueError`` si la trame est syntaxiquement invalide pour ce
        protocole, ``NotImplementedError`` si le parseur n'est pas encore prêt.
        """
