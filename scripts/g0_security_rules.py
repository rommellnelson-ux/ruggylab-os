"""Règles curées de la baseline de sécurité G0 — la partie qui se relit.

Ce module ne calcule rien. Il porte les tables de correspondance que
`scripts/g0_security_baseline.py` applique : sémantique des gardes, rattachement
des tables aux routes, classification des champs, frontières externes,
qualification des routes particulières, revue de `.secrets.baseline`.

Pourquoi les séparer du générateur ? Parce que ce sont deux natures de preuve
différentes. Le générateur est *vérifiable par exécution* : on le relance et on
compare. Ces tables-ci sont *vérifiables par lecture* : elles engagent un
jugement humain, elles doivent être relues ligne à ligne, et les mélanger au
code d'exécution rendrait la relecture impraticable.

Rien ici n'est une valeur de secret. Rien ici n'est une donnée patient. La revue
de `.secrets.baseline` désigne des emplacements et porte un jugement ; elle ne
recopie aucune valeur, même tronquée — une valeur tronquée reste un indice.
"""

from __future__ import annotations

from typing import Any

# ── 1. Sémantique des gardes ────────────────────────────────────────────────
#
# Les quatre rôles de l'application, tels que `app/models/ruggylab_os.py` les
# définit. L'ordre est fixé pour que les listes produites soient comparables.
ROLES: tuple[str, ...] = ("accountant", "admin", "officer", "technician")

#: Ce que chaque dépendance FastAPI autorise réellement, lu dans
#: `app/api/deps.py`. Une garde absente de cette table fait échouer le
#: générateur : mieux vaut refuser de produire une matrice que d'en produire une
#: qui range une garde inconnue du côté rassurant.
SEMANTIQUE_GARDES: dict[str, dict[str, Any]] = {
    "get_current_user": {
        "nature": "authentication",
        "roles_autorises": ROLES,
        "description": (
            "Décode le JWT, refuse un jeton révoqué (denylist par jti) et un "
            "jeton dont `ver` ne correspond plus à `user.auth_version`. "
            "N'exerce AUCUN contrôle de rôle."
        ),
    },
    "get_current_active_user": {
        "nature": "authentication",
        "roles_autorises": ROLES,
        "description": "Refuse un compte désactivé (403). Aucun contrôle de rôle.",
    },
    "require_admin": {
        "nature": "authorization",
        "roles_autorises": ("admin",),
        "description": "role == ADMIN, sinon 403.",
    },
    "require_officer": {
        "nature": "authorization",
        "roles_autorises": ("admin", "officer"),
        "description": "role ∈ {OFFICER, ADMIN}, sinon 403.",
    },
    "require_finance": {
        "nature": "authorization",
        "roles_autorises": ("accountant", "admin"),
        "description": "role ∈ {ACCOUNTANT, ADMIN}, sinon 403. Séparation des tâches.",
    },
    "forbid_accountant": {
        "nature": "authorization",
        "roles_autorises": ("admin", "officer", "technician"),
        "description": "role != ACCOUNTANT, sinon 403. Cloisonnement clinique / gestion.",
    },
    "_verify_analyzer_security": {
        "nature": "machine_token",
        "roles_autorises": (),
        "description": (
            "Garde propre à l'ingestion automate : exige ANALYZER_API_KEY "
            "(comparaison à temps constant), filtre optionnel d'IP "
            "(ANALYZER_ALLOWED_IPS) et signature HMAC-SHA256 horodatée "
            "optionnelle (ANALYZER_HMAC_SECRET). Aucun compte utilisateur, "
            "aucun rôle : ce n'est pas une identité humaine."
        ),
    },
}

#: Dépendances qui n'ont aucun rôle dans l'autorisation. Les lister évite de les
#: confondre avec une garde : `get_db` ouvre une session, il ne protège rien, et
#: `OAuth2PasswordBearer` ne fait qu'extraire l'en-tête.
DEPENDANCES_NON_AUTORISANTES: frozenset[str] = frozenset(
    {
        "get_db",
        "OAuth2PasswordBearer",
        "OAuth2PasswordRequestForm",
        "get_prescription_scanner",
        "get_billing_engine",
        "get_stock_predictor",
        "get_stock_notifier",
    }
)

# ── 2. Rattachement des tables aux routes ───────────────────────────────────
#
# Sert à MESURER les acteurs qui atteignent une donnée, au lieu de l'affirmer :
# les rôles autorisés sur une table sont l'union des rôles autorisés sur les
# routes qui la servent. Le rattachement lui-même est curé et se relit ; le
# calcul des rôles, lui, vient de la matrice.
TABLE_VERS_ROUTES: dict[str, tuple[str, ...]] = {
    "aes_incidents": ("/api/v1/aes",),
    "audit_events": ("/api/v1/audit-events", "/api/v1/reports/audit"),
    "auto_validation_configs": ("/api/v1/auto-validation",),
    "biological_code_mappings": ("/api/v1/code-mappings",),
    "biological_reference_ranges": ("/api/v1/bioref",),
    "bnpl_payments": ("/api/v1/billing/bnpl",),
    "bnpl_schedules": ("/api/v1/billing/bnpl", "/api/v1/invoices/{invoice_id}/payment-plan"),
    "corrective_actions": ("/api/v1/quality",),
    "critical_ranges": ("/api/v1/critical-ranges", "/api/v1/critical-alerts"),
    "delta_check_rules": ("/api/v1/delta-check-rules",),
    "dh36_inbound_messages": ("/api/v1/dh36", "/api/v1/analyzer"),
    "epi_notifications": ("/api/v1/epi-notifications", "/api/v1/reports/epidemiology"),
    "equipment_approved_analytes": ("/api/v1/equipments",),
    "equipment_documents": ("/api/v1/equipments",),
    "equipment_interfaces": ("/api/v1/equipments",),
    "equipment_maintenances": ("/api/v1/equipment-maintenance",),
    "equipment_qualifications": ("/api/v1/equipments",),
    "equipment_reagent_ratio_versions": ("/api/v1/equipment-reagent-ratios",),
    "equipment_reagent_ratios": ("/api/v1/equipment-reagent-ratios", "/api/v1/admin/ratios"),
    "equipments": ("/api/v1/equipments", "/api/v1/equipment-maintenance"),
    "exam_order_items": ("/api/v1/exam-orders", "/api/v1/worklist"),
    "exam_orders": (
        "/api/v1/exam-orders",
        "/api/v1/operations/validate-order",
        "/api/v1/worklist",
    ),
    "exam_tariffs": ("/api/v1/tariffs", "/api/v1/billing/calculate"),
    "invoice_lines": ("/api/v1/invoices",),
    "invoice_payments": ("/api/v1/invoices",),
    "invoices": ("/api/v1/invoices", "/api/v1/exam-orders/{order_id}/invoice"),
    "malaria_analysis_jobs": ("/api/v1/imaging",),
    "non_conformities": ("/api/v1/quality",),
    "notif_configs": ("/api/v1/critical-alerts/config",),
    "patients": (
        "/api/v1/patients",
        "/api/v1/bulk-import/patients",
        "/api/v1/registre",
    ),
    "qc_controls": ("/api/v1/qc", "/api/v1/reports/qc"),
    "qc_results": ("/api/v1/qc", "/api/v1/reports/qc"),
    "ratio_preset_items": ("/api/v1/ratio-presets",),
    "ratio_presets": ("/api/v1/ratio-presets",),
    "reagent_lots": ("/api/v1/reagent-lots", "/api/v1/reagents"),
    "reagents": (
        "/api/v1/reagents",
        "/api/v1/reagent-lots",
        "/api/v1/stock",
        "/api/v1/reports/stock",
        "/api/v1/reports/critical-thresholds",
    ),
    "reference_ranges": ("/api/v1/reference-ranges",),
    "refresh_tokens": ("/api/v1/login", "/api/v1/maintenance"),
    "report_signatures": ("/api/v1/reports/results",),
    "report_snapshots": ("/api/v1/reports/snapshots", "/api/v1/reports/verify"),
    "results": (
        "/api/v1/results",
        "/api/v1/reports/results",
        "/api/v1/tat/results",
        "/api/v1/imaging",
    ),
    "revoked_tokens": ("/api/v1/login", "/api/v1/maintenance"),
    "samples": ("/api/v1/samples", "/api/v1/exam-orders"),
    "stock_movements": ("/api/v1/stock", "/api/v1/reagent-lots", "/api/v1/reports/stock"),
    "tat_targets": ("/api/v1/tat",),
    "users": ("/api/v1/users", "/api/v1/admin"),
    # Tables sans route directe. Ne pas les déclarer serait plus confortable
    # qu'exact : elles existent, elles portent des données, et le fait qu'aucune
    # route ne les serve est un constat, pas une absence.
    "alembic_version": (),
    "csa_sync_state": (),
    "report_delivery_outbox": (),
}

# ── 3. Classification des champs ────────────────────────────────────────────

CATEGORIES: tuple[str, ...] = (
    "IDENTITE",
    "DONNEE_DE_SANTE",
    "RESULTAT_BIOLOGIQUE",
    "AUTHENTIFICATION_SECRET",
    "FINANCIER",
    "AUDIT",
    "OPERATIONNEL_MILITAIRE",
    "TECHNIQUE",
    "NON_SENSIBLE",
    "A_QUALIFIER",
)

#: Classification explicite d'un champ précis. Prime sur toute règle de nom.
#: Chaque entrée porte sa finalité **observée dans le code**, pas supposée.
SURCHARGES_COLONNES: dict[tuple[str, str], tuple[str, str]] = {
    # — patients —
    ("patients", "ipp_unique_id"): ("IDENTITE", "Identifiant permanent du patient."),
    ("patients", "first_name"): ("IDENTITE", "Prénom en clair."),
    ("patients", "last_name"): ("IDENTITE", "Nom en clair."),
    ("patients", "birth_date"): ("IDENTITE", "Date de naissance."),
    ("patients", "birth_date_estimee"): (
        "TECHNIQUE",
        "Marque une date de naissance estimée faute de source.",
    ),
    ("patients", "sex"): ("IDENTITE", "Sexe déclaré."),
    ("patients", "phone"): ("IDENTITE", "Numéro de téléphone."),
    ("patients", "rank"): (
        "OPERATIONNEL_MILITAIRE",
        "Grade militaire — rattache la personne à la hiérarchie.",
    ),
    ("patients", "unit"): (
        "OPERATIONNEL_MILITAIRE",
        "Unité de rattachement ; sert aussi de clé de cloisonnement RBAC.",
    ),
    ("patients", "residence_quarter"): (
        "IDENTITE",
        "Quartier de résidence — donnée de localisation, exploitée en cartographie épidémiologique.",
    ),
    # — AES : dossier d'exposition professionnelle —
    ("aes_incidents", "agent_label"): ("IDENTITE", "Agent exposé, en texte libre."),
    ("aes_incidents", "agent_user_id"): ("IDENTITE", "Agent exposé, par référence au compte."),
    ("aes_incidents", "source_label"): (
        "IDENTITE",
        "Patient source de l'exposition, en texte libre.",
    ),
    ("aes_incidents", "source_serology"): (
        "DONNEE_DE_SANTE",
        "Statut sérologique VIH / VHB / VHC du patient source. Donnée de santé "
        "parmi les plus sensibles du schéma.",
    ),
    ("aes_incidents", "circumstances"): (
        "DONNEE_DE_SANTE",
        "Récit libre de l'accident — champ texte non contraint, susceptible de "
        "contenir des identités et des éléments cliniques.",
    ),
    ("aes_incidents", "immediate_measures"): (
        "DONNEE_DE_SANTE",
        "Conduite tenue après exposition.",
    ),
    ("aes_incidents", "followup_notes"): ("DONNEE_DE_SANTE", "Suivi médical de l'agent exposé."),
    ("aes_incidents", "exposure_type"): ("DONNEE_DE_SANTE", "Nature de l'exposition."),
    ("aes_incidents", "location"): ("OPERATIONNEL_MILITAIRE", "Lieu de survenue."),
    # — épidémiologie —
    ("epi_notifications", "pathology"): ("DONNEE_DE_SANTE", "Pathologie à déclaration."),
    ("epi_notifications", "patient_label"): ("IDENTITE", "Patient désigné en texte libre."),
    ("epi_notifications", "patient_id"): ("IDENTITE", "Référence au dossier patient."),
    ("epi_notifications", "residence_quarter"): ("IDENTITE", "Quartier de résidence."),
    ("epi_notifications", "sample_barcode"): (
        "TECHNIQUE",
        "Code-barres échantillon — réidentifiant indirect.",
    ),
    ("epi_notifications", "channel"): ("TECHNIQUE", "Canal de transmission."),
    # — résultats —
    ("results", "data_points"): ("RESULTAT_BIOLOGIQUE", "Valeurs mesurées, JSON par analyte."),
    ("results", "flags"): ("RESULTAT_BIOLOGIQUE", "Drapeaux d'interprétation par analyte."),
    ("results", "delta_analytes"): ("RESULTAT_BIOLOGIQUE", "Analytes en écart delta."),
    ("results", "is_critical"): ("RESULTAT_BIOLOGIQUE", "Présence d'une valeur critique."),
    ("results", "bioref_comment"): ("RESULTAT_BIOLOGIQUE", "Commentaire d'interprétation."),
    ("results", "bioref_status"): ("RESULTAT_BIOLOGIQUE", "Position vis-à-vis des bornes."),
    ("results", "bioref_reference_range"): ("RESULTAT_BIOLOGIQUE", "Intervalle appliqué."),
    ("results", "exam_code"): (
        "DONNEE_DE_SANTE",
        "Examen réalisé — révèle l'orientation clinique.",
    ),
    ("results", "result_type"): ("DONNEE_DE_SANTE", "Nature de l'examen."),
    ("results", "amendment_reason"): (
        "AUDIT",
        "Motif de correction d'un résultat déjà rendu — pièce de traçabilité ISO 15189.",
    ),
    ("results", "image_url"): (
        "DONNEE_DE_SANTE",
        "Chemin de l'image de microscopie associée au résultat.",
    ),
    ("results", "validator_id"): ("AUDIT", "Auteur de la validation biologique."),
    ("results", "critical_ack_by_id"): ("AUDIT", "Auteur de l'acquittement critique."),
    # — échantillons / prescriptions —
    ("samples", "barcode"): ("TECHNIQUE", "Code-barres — réidentifiant indirect du dossier."),
    ("samples", "lab_number"): ("TECHNIQUE", "Numéro de laboratoire — réidentifiant indirect."),
    ("samples", "collected_by_label"): ("IDENTITE", "Nom du préleveur, en texte libre."),
    ("samples", "aspect"): ("DONNEE_DE_SANTE", "Qualité pré-analytique de l'échantillon."),
    ("exam_orders", "clinical_info"): (
        "DONNEE_DE_SANTE",
        "Renseignement clinique libre accompagnant la demande.",
    ),
    ("exam_orders", "prescriber"): ("IDENTITE", "Prescripteur, en texte libre."),
    ("exam_orders", "requesting_service"): ("OPERATIONNEL_MILITAIRE", "Service demandeur."),
    ("exam_orders", "csa_prescription_id"): (
        "TECHNIQUE",
        "Corrélation avec la prescription CSA — clé de rapprochement inter-systèmes.",
    ),
    ("exam_order_items", "exam_code"): ("DONNEE_DE_SANTE", "Examen demandé."),
    ("exam_order_items", "exam_label"): ("DONNEE_DE_SANTE", "Libellé de l'examen demandé."),
    # — comptes rendus —
    ("report_snapshots", "content_snapshot"): (
        "RESULTAT_BIOLOGIQUE",
        "Copie figée du compte rendu : identité patient ET valeurs mesurées.",
    ),
    ("report_snapshots", "verification_token_hash"): (
        "AUTHENTIFICATION_SECRET",
        "Empreinte SHA-256 du jeton de vérification publique. Le jeton lui-même "
        "n'est pas stocké ; il est recalculable par HMAC depuis SECRET_KEY.",
    ),
    ("report_snapshots", "verification_path"): (
        "TECHNIQUE",
        "Chemin public de vérification — contient le jeton en clair dans l'URL.",
    ),
    ("report_snapshots", "pdf_sha256"): ("TECHNIQUE", "Empreinte du PDF rendu."),
    ("report_signatures", "signature_hash"): (
        "AUDIT",
        "Signature du compte rendu — preuve d'intégrité et d'auteur.",
    ),
    ("report_signatures", "report_hash"): ("AUDIT", "Empreinte du contenu signé."),
    ("report_delivery_outbox", "payload"): (
        "A_QUALIFIER",
        "Charge utile de la remise du compte rendu. Le contenu dépend du canal ; "
        "aucune contrainte de schéma n'interdit d'y placer des données patient.",
    ),
    ("report_delivery_outbox", "idempotency_key"): ("TECHNIQUE", "Clé d'idempotence de remise."),
    ("report_delivery_outbox", "last_error"): (
        "A_QUALIFIER",
        "Message d'erreur du canal de remise, stocké tel quel — peut contenir "
        "une adresse de destinataire ou un extrait de charge utile.",
    ),
    # — authentification —
    ("users", "hashed_password"): (
        "AUTHENTIFICATION_SECRET",
        "Empreinte du mot de passe (bcrypt).",
    ),
    ("users", "username"): ("IDENTITE", "Identifiant de connexion."),
    ("users", "full_name"): ("IDENTITE", "Nom complet de l'agent."),
    ("users", "role"): ("TECHNIQUE", "Rôle RBAC — détermine toute l'autorisation."),
    ("users", "unit"): ("OPERATIONNEL_MILITAIRE", "Unité de rattachement de l'agent."),
    ("users", "auth_version"): (
        "AUTHENTIFICATION_SECRET",
        "Version de sécurité du compte ; incrémentée pour invalider les jetons.",
    ),
    ("users", "is_active"): ("TECHNIQUE", "Compte actif ou suspendu."),
    ("refresh_tokens", "token_hash"): (
        "AUTHENTIFICATION_SECRET",
        "Empreinte du jeton de rafraîchissement ; le jeton brut n'est jamais stocké.",
    ),
    ("revoked_tokens", "jti"): (
        "AUTHENTIFICATION_SECRET",
        "Identifiant du jeton d'accès révoqué (denylist).",
    ),
    # — financier —
    ("invoices", "patient_label"): ("IDENTITE", "Patient facturé, en texte libre."),
    ("invoices", "patient_id"): ("IDENTITE", "Référence au dossier patient."),
    ("invoices", "insurance_id"): ("FINANCIER", "Référence assurance / CMU."),
    ("invoices", "patient_type"): (
        "OPERATIONNEL_MILITAIRE",
        "Catégorie de bénéficiaire (militaire, ayant droit, civil).",
    ),
    ("invoice_lines", "exam_code"): (
        "DONNEE_DE_SANTE",
        "Examen facturé : une ligne de facture révèle l'examen réalisé. "
        "C'est par ce champ que la facturation touche à la donnée de santé.",
    ),
    ("invoice_lines", "label"): ("DONNEE_DE_SANTE", "Libellé de l'examen facturé."),
    ("bnpl_schedules", "patient_ref"): ("IDENTITE", "Référence patient de l'échéancier."),
    ("bnpl_schedules", "prescriber_id"): ("IDENTITE", "Prescripteur associé."),
    # — audit —
    ("audit_events", "payload"): (
        "AUDIT",
        "Détail de l'événement, en JSON libre. Le contenu dépend de l'appelant : "
        "aucune contrainte de schéma n'empêche d'y écrire une donnée patient.",
    ),
    ("audit_events", "entity_id"): ("AUDIT", "Objet concerné — réidentifiant indirect."),
    ("audit_events", "user_id"): ("AUDIT", "Auteur de l'action."),
    ("audit_events", "event_type"): ("AUDIT", "Nature de l'action."),
    # — automates —
    ("dh36_inbound_messages", "raw_message"): (
        "RESULTAT_BIOLOGIQUE",
        "Trame brute de l'automate : contient les valeurs mesurées et le "
        "code-barres de l'échantillon.",
    ),
    ("dh36_inbound_messages", "rejection_reason"): (
        "A_QUALIFIER",
        "Motif de rejet stocké tel quel — peut reprendre un extrait de trame.",
    ),
    ("dh36_inbound_messages", "sample_barcode"): (
        "TECHNIQUE",
        "Code-barres — réidentifiant indirect.",
    ),
    ("dh36_inbound_messages", "equipment_serial"): ("TECHNIQUE", "Numéro de série de l'automate."),
    # — imagerie —
    ("malaria_analysis_jobs", "image_url"): (
        "DONNEE_DE_SANTE",
        "Chemin de la lame numérisée.",
    ),
    ("malaria_analysis_jobs", "prediction_label"): (
        "RESULTAT_BIOLOGIQUE",
        "Prédiction du modèle — assistance, jamais un résultat validé.",
    ),
    ("malaria_analysis_jobs", "confidence"): ("RESULTAT_BIOLOGIQUE", "Score du modèle."),
    ("malaria_analysis_jobs", "error_message"): (
        "A_QUALIFIER",
        "Message d'erreur du moteur d'inférence, stocké tel quel.",
    ),
    # — qualité —
    ("non_conformities", "description"): (
        "A_QUALIFIER",
        "Description libre d'une non-conformité — champ texte non contraint, "
        "susceptible de nommer un patient ou un agent.",
    ),
    ("non_conformities", "root_cause"): ("A_QUALIFIER", "Analyse de cause, en texte libre."),
    ("non_conformities", "linked_entity_id"): (
        "TECHNIQUE",
        "Objet rattaché — réidentifiant indirect.",
    ),
    ("corrective_actions", "description"): ("A_QUALIFIER", "Action corrective, en texte libre."),
    ("corrective_actions", "effectiveness_notes"): ("A_QUALIFIER", "Vérification d'efficacité."),
    ("qc_results", "operator"): ("IDENTITE", "Opérateur du contrôle, en texte libre."),
    ("qc_results", "value"): (
        "NON_SENSIBLE",
        "Valeur d'un contrôle de qualité : matériel de contrôle, pas un patient.",
    ),
    # — équipements et interfaces —
    ("equipments", "location"): (
        "OPERATIONNEL_MILITAIRE",
        "Emplacement physique de l'automate dans l'établissement.",
    ),
    ("equipments", "unit"): ("OPERATIONNEL_MILITAIRE", "Unité de rattachement."),
    ("equipment_interfaces", "endpoint_reference"): (
        "A_QUALIFIER",
        "Référence du point de connexion de l'automate — peut porter une adresse réseau interne.",
    ),
    ("equipment_documents", "storage_reference"): ("TECHNIQUE", "Emplacement du document."),
    # — synchronisation CSA —
    ("csa_sync_state", "last_error"): (
        "A_QUALIFIER",
        "Dernière erreur de synchronisation entrante, stockée telle quelle — "
        "peut reprendre un extrait de charge utile CSA.",
    ),
    ("csa_sync_state", "last_outbound_error"): (
        "A_QUALIFIER",
        "Dernière erreur de synchronisation sortante, stockée telle quelle.",
    ),
    # — notifications —
    ("notif_configs", "email"): ("IDENTITE", "Adresse de destinataire des alertes."),
    ("notif_configs", "webhook_url"): (
        "AUTHENTIFICATION_SECRET",
        "URL de webhook : peut porter un jeton dans son chemin ou sa requête.",
    ),
}

#: Règles par nom de colonne, appliquées dans l'ordre quand aucune surcharge ne
#: s'applique. Le motif est comparé au nom EXACT ou en suffixe/préfixe explicite,
#: jamais par sous-chaîne libre — `id` ne doit pas capturer `invoice_id`.
REGLES_NOMS: tuple[tuple[str, str, str, str], ...] = (
    # (genre, motif, catégorie, finalité)
    ("exact", "id", "TECHNIQUE", "Clé primaire technique."),
    ("exact", "version_num", "TECHNIQUE", "Révision Alembic appliquée."),
    ("suffixe", "_by_id", "AUDIT", "Auteur d'une action — traçabilité."),
    ("suffixe", "_by_user_id", "AUDIT", "Auteur d'une action — traçabilité."),
    ("exact", "created_by_id", "AUDIT", "Auteur de la création."),
    ("exact", "detected_by_id", "AUDIT", "Auteur de la détection."),
    ("exact", "declared_by_id", "AUDIT", "Auteur de la déclaration."),
    ("exact", "responsible_id", "AUDIT", "Responsable désigné."),
    ("exact", "user_id", "AUDIT", "Compte à l'origine de l'enregistrement."),
    ("suffixe", "_xof", "FINANCIER", "Montant en francs CFA."),
    ("exact", "amount", "FINANCIER", "Montant."),
    ("exact", "price", "FINANCIER", "Prix unitaire."),
    ("exact", "quantity", "NON_SENSIBLE", "Quantité de stock ou de ligne."),
    ("suffixe", "_hash", "AUTHENTIFICATION_SECRET", "Empreinte cryptographique."),
    ("suffixe", "_secret", "AUTHENTIFICATION_SECRET", "Élément secret."),
    ("suffixe", "_token", "AUTHENTIFICATION_SECRET", "Jeton."),
    ("suffixe", "_id", "TECHNIQUE", "Clé étrangère technique."),
    ("suffixe", "_at", "TECHNIQUE", "Horodatage d'étape."),
    ("suffixe", "_date", "TECHNIQUE", "Date d'étape."),
    ("exact", "status", "TECHNIQUE", "État de workflow."),
    ("exact", "is_active", "TECHNIQUE", "Activation de l'enregistrement."),
    ("prefixe", "is_", "TECHNIQUE", "Drapeau booléen d'état."),
    ("prefixe", "has_", "TECHNIQUE", "Drapeau booléen d'état."),
    ("prefixe", "snapshot_", "TECHNIQUE", "Copie figée d'un attribut d'équipement."),
    ("exact", "notes", "A_QUALIFIER", "Champ texte libre, sans contrainte de contenu."),
    ("exact", "description", "A_QUALIFIER", "Champ texte libre, sans contrainte de contenu."),
    ("exact", "comment", "A_QUALIFIER", "Champ texte libre, sans contrainte de contenu."),
    ("suffixe", "_reason", "AUDIT", "Motif d'une décision — pièce de traçabilité."),
    ("suffixe", "_notes", "A_QUALIFIER", "Champ texte libre, sans contrainte de contenu."),
    ("suffixe", "_error", "A_QUALIFIER", "Message d'erreur stocké tel quel."),
    ("exact", "unit", "NON_SENSIBLE", "Unité de mesure de l'analyte."),
    ("exact", "name", "NON_SENSIBLE", "Libellé d'un objet de référentiel."),
    ("exact", "label", "NON_SENSIBLE", "Libellé d'un objet de référentiel."),
    ("exact", "category", "NON_SENSIBLE", "Catégorie de référentiel."),
)

#: Catégorie par défaut d'une TABLE, appliquée quand ni surcharge ni règle de
#: nom ne tranche. Elle porte la nature de la table, pas celle du champ : un
#: champ d'une table de référentiel n'est pas une donnée personnelle, quel que
#: soit son nom.
#:
#: Une table absente de cette map retombe sur `CATEGORIE_PAR_DEFAUT`, donc sur
#: `A_QUALIFIER` : on ne range jamais par défaut du côté rassurant.
CATEGORIE_PAR_DEFAUT_TABLE: dict[str, tuple[str, str]] = {
    # Référentiels et paramétrages : ne concernent aucune personne.
    "auto_validation_configs": ("NON_SENSIBLE", "Règle d'auto-validation — paramétrage."),
    "biological_code_mappings": ("NON_SENSIBLE", "Correspondance de codes d'examen."),
    "biological_reference_ranges": ("NON_SENSIBLE", "Intervalle de référence — référentiel."),
    "critical_ranges": ("NON_SENSIBLE", "Borne critique — référentiel."),
    "delta_check_rules": ("NON_SENSIBLE", "Règle de contrôle delta — référentiel."),
    "reference_ranges": ("NON_SENSIBLE", "Intervalle de référence — référentiel."),
    "exam_tariffs": ("NON_SENSIBLE", "Tarif d'examen — référentiel."),
    "tat_targets": ("NON_SENSIBLE", "Objectif de délai — référentiel."),
    "qc_controls": ("NON_SENSIBLE", "Matériel de contrôle — référentiel."),
    "qc_results": ("NON_SENSIBLE", "Mesure sur matériel de contrôle, jamais sur un patient."),
    "ratio_presets": ("NON_SENSIBLE", "Préréglage de consommation — référentiel."),
    "ratio_preset_items": ("NON_SENSIBLE", "Préréglage de consommation — référentiel."),
    "equipment_reagent_ratios": ("NON_SENSIBLE", "Ratio de consommation — paramétrage."),
    "equipment_reagent_ratio_versions": ("NON_SENSIBLE", "Version d'un ratio — paramétrage."),
    "notif_configs": ("TECHNIQUE", "Paramétrage des notifications."),
    "alembic_version": ("TECHNIQUE", "État des migrations."),
    # Stock.
    "reagents": ("NON_SENSIBLE", "Gestion de stock de réactifs."),
    "reagent_lots": ("NON_SENSIBLE", "Lot de réactif — gestion de stock."),
    "stock_movements": ("NON_SENSIBLE", "Mouvement de stock."),
    # Parc d'équipements et métrologie.
    "equipments": ("TECHNIQUE", "Parc d'équipements."),
    "equipment_documents": ("TECHNIQUE", "Documentation d'équipement."),
    "equipment_interfaces": ("TECHNIQUE", "Interface d'automate."),
    "equipment_qualifications": ("TECHNIQUE", "Qualification métrologique."),
    "equipment_approved_analytes": ("TECHNIQUE", "Analyte approuvé sur un équipement."),
    "equipment_maintenances": ("TECHNIQUE", "Maintenance d'équipement."),
    # Technique et exploitation.
    "csa_sync_state": ("TECHNIQUE", "État de la synchronisation CSA."),
    "dh36_inbound_messages": ("TECHNIQUE", "Message entrant d'automate."),
    "malaria_analysis_jobs": ("TECHNIQUE", "Tâche d'inférence sur image."),
    "report_delivery_outbox": ("TECHNIQUE", "File de remise des comptes rendus."),
    "report_snapshots": ("TECHNIQUE", "Métadonnée de compte rendu figé."),
    "report_signatures": ("AUDIT", "Signature de compte rendu — traçabilité."),
    "non_conformities": ("TECHNIQUE", "Non-conformité qualité."),
    "corrective_actions": ("TECHNIQUE", "Action corrective."),
    "audit_events": ("AUDIT", "Événement d'audit."),
    # Métier sensible.
    "results": ("RESULTAT_BIOLOGIQUE", "Attribut d'un résultat biologique."),
    "exam_orders": ("DONNEE_DE_SANTE", "Attribut d'une demande d'examen."),
    "exam_order_items": ("DONNEE_DE_SANTE", "Ligne d'une demande d'examen."),
    "invoices": ("FINANCIER", "Attribut de facture."),
    "invoice_lines": ("FINANCIER", "Ligne de facture."),
    "invoice_payments": ("FINANCIER", "Encaissement."),
    "bnpl_schedules": ("FINANCIER", "Échéancier de paiement."),
    "bnpl_payments": ("FINANCIER", "Échéance de paiement."),
}

#: Catégorie retenue quand ni surcharge, ni règle de nom, ni défaut de table ne
#: s'applique. Volontairement `A_QUALIFIER` et non `NON_SENSIBLE` : un champ
#: qu'on ne sait pas classer doit être examiné, pas rangé du côté rassurant.
CATEGORIE_PAR_DEFAUT = ("A_QUALIFIER", "Non couvert par une règle ni par une surcharge.")

# ── 4. Contexte par table ───────────────────────────────────────────────────
#
# Ce qui ne se lit pas dans le schéma : par où la donnée entre, par où elle
# sort, ce qu'il en reste. `duree_conservation` vaut UNKNOWN partout où le dépôt
# n'en définit aucune — et il n'en définit qu'une seule.
_SAUVEGARDE_TOTALE = (
    "Incluse dans le dump pg_dump du service `db-backup` (base entière, "
    "aucune exclusion par table)."
)

CONTEXTE_TABLES: dict[str, dict[str, str]] = {
    "patients": {
        "flux_entrant": "Saisie cockpit, import registre, import en masse, prescription CSA (désactivée).",
        "flux_sortant": "API JSON, bundle FHIR patient, export épidémiologie CSV, PDF de compte rendu.",
        "journalisation": "audit_events sur création et modification ; l'identifiant figure dans le chemin journalisé par ObservabilityMiddleware.",
        "metriques": "patients_count (compteur global, sans étiquette nominative).",
        "duree_conservation": "UNKNOWN",
    },
    "results": {
        "flux_entrant": "Saisie cockpit, ingestion automate (désactivée), POCT, imagerie.",
        "flux_sortant": "API JSON, FHIR, PDF de compte rendu, export CSV, WebSocket d'alertes critiques.",
        "journalisation": "audit_events sur validation, correction, libération.",
        "metriques": "results_count (compteur global).",
        "duree_conservation": "UNKNOWN",
    },
    "samples": {
        "flux_entrant": "Saisie cockpit, code-barres, prescription CSA (désactivée).",
        "flux_sortant": "API JSON, étiquettes code-barres imprimées, export registre.",
        "journalisation": "audit_events sur création et changement d'état.",
        "metriques": "samples_count (compteur global).",
        "duree_conservation": "UNKNOWN",
    },
    "aes_incidents": {
        "flux_entrant": "Déclaration par formulaire authentifié.",
        "flux_sortant": "API JSON réservée aux officiers et administrateurs.",
        "journalisation": "aucun enregistrement d'audit dédié observé.",
        "metriques": "aucune.",
        "duree_conservation": "UNKNOWN",
    },
    "epi_notifications": {
        "flux_entrant": "Déclaration par formulaire authentifié.",
        "flux_sortant": "API JSON, export CSV d'épidémiologie, transmission ONMCI (fail-closed).",
        "journalisation": "audit_events sur transmission.",
        "metriques": "aucune.",
        "duree_conservation": "UNKNOWN",
    },
    "audit_events": {
        "flux_entrant": "Écrit par les services applicatifs à chaque action tracée.",
        "flux_sortant": "API JSON et export CSV, réservés à l'administrateur.",
        "journalisation": "table d'audit elle-même ; aucun journal du journal.",
        "metriques": "audit_events_total.",
        "duree_conservation": "UNKNOWN",
    },
    "users": {
        "flux_entrant": "Création par l'administrateur ; amorçage du premier compte au démarrage.",
        "flux_sortant": "API JSON réservée à l'administrateur ; `/users/me` pour le porteur du jeton.",
        "journalisation": "audit_events sur création et modification.",
        "metriques": "active_users.",
        "duree_conservation": "UNKNOWN",
    },
    "refresh_tokens": {
        "flux_entrant": "Créés à chaque connexion et à chaque rotation.",
        "flux_sortant": "jamais renvoyés en lecture ; seule l'empreinte est stockée.",
        "journalisation": "aucune.",
        "metriques": "aucune.",
        "duree_conservation": "7 jours après expiration (purge planifiée, token_cleanup._DEFAULT_KEEP_DAYS).",
    },
    "revoked_tokens": {
        "flux_entrant": "Écrits à la déconnexion (denylist par jti).",
        "flux_sortant": "jamais renvoyés en lecture.",
        "journalisation": "aucune.",
        "metriques": "aucune.",
        "duree_conservation": "purgés après expiration du jeton (purge_expired_revocations).",
    },
    "invoices": {
        "flux_entrant": "Facturation d'une demande d'examen.",
        "flux_sortant": "API JSON, export CSV, reçu PDF.",
        "journalisation": "audit_events sur émission, encaissement, annulation, avoir.",
        "metriques": "aucune.",
        "duree_conservation": "UNKNOWN",
    },
    "report_snapshots": {
        "flux_entrant": "Figés à la libération d'un compte rendu.",
        "flux_sortant": "PDF, vérification publique par jeton, file de remise.",
        "journalisation": "audit_events sur libération et révocation.",
        "metriques": "aucune.",
        "duree_conservation": "UNKNOWN — l'immuabilité impose la conservation, aucune borne n'est définie.",
    },
    "dh36_inbound_messages": {
        "flux_entrant": "Trames d'automate — interface désactivée par défaut.",
        "flux_sortant": "aucune route de lecture.",
        "journalisation": "aucune.",
        "metriques": "aucune.",
        "duree_conservation": "UNKNOWN",
    },
    "report_delivery_outbox": {
        "flux_entrant": "Écrit à la libération d'un compte rendu.",
        "flux_sortant": "canal de remise externe, traité par un worker hors application.",
        "journalisation": "aucune.",
        "metriques": "aucune.",
        "duree_conservation": "UNKNOWN",
    },
    "csa_sync_state": {
        "flux_entrant": "Écrit par la synchronisation CSA — désactivée par défaut.",
        "flux_sortant": "aucune route.",
        "journalisation": "aucune.",
        "metriques": "aucune.",
        "duree_conservation": "UNKNOWN",
    },
}

#: Contexte appliqué à toute table qui n'a pas d'entrée explicite ci-dessus.
CONTEXTE_TABLE_DEFAUT: dict[str, str] = {
    "flux_entrant": "Écritures par l'API authentifiée.",
    "flux_sortant": "Lectures par l'API authentifiée.",
    "journalisation": "Non observée spécifiquement pour cette table.",
    "metriques": "aucune étiquette de métrique dérivée de cette table.",
    "duree_conservation": "UNKNOWN",
}

#: Stockage et chiffrement : constatés une fois, identiques pour toute la base.
STOCKAGE_COMMUN = {
    "stockage": "PostgreSQL 16, volume Docker local, aucun chiffrement au repos observé.",
    "chiffrement_observe": (
        "En transit : TLS entre le navigateur et le proxy Caddy uniquement. "
        "Proxy → application, application → PostgreSQL et application → Valkey "
        "circulent en clair sur le réseau Docker interne. Au repos : aucun "
        "chiffrement de colonne, aucun chiffrement de volume, dump de sauvegarde "
        "non chiffré."
    ),
    "sauvegarde": _SAUVEGARDE_TOTALE,
}

#: Risque par catégorie. Uniforme et assumé : il qualifie la nature de la
#: donnée, pas la qualité de la protection — celle-ci est dite par la matrice.
RISQUE_PAR_CATEGORIE: dict[str, str] = {
    "IDENTITE": "ELEVE",
    "DONNEE_DE_SANTE": "ELEVE",
    "RESULTAT_BIOLOGIQUE": "ELEVE",
    "AUTHENTIFICATION_SECRET": "ELEVE",
    "OPERATIONNEL_MILITAIRE": "ELEVE",
    "FINANCIER": "MOYEN",
    "AUDIT": "MOYEN",
    "A_QUALIFIER": "MOYEN",
    "TECHNIQUE": "FAIBLE",
    "NON_SENSIBLE": "FAIBLE",
}

# ── 5. Frontières externes ──────────────────────────────────────────────────
#
# Les douze frontières recensées par le lot A (docs/g0/INVENTORY.md §6),
# reprises une par une et complétées par les données transportées. Le lot A
# s'arrêtait aux frontières techniques ; il annonçait ce détail pour le lot B.
FLUX_EXTERNES: tuple[dict[str, Any], ...] = (
    {
        "id": "navigateur_vers_proxy",
        "frontiere_lot_a": "Navigateur → proxy",
        "origine": "navigateur du poste client (LAN de l'établissement)",
        "destination": "proxy Caddy (443/TCP)",
        "protocole": "HTTPS",
        "declencheur": "usage interactif",
        "etat_par_defaut": "actif",
        "categories_donnees": [
            "IDENTITE",
            "DONNEE_DE_SANTE",
            "RESULTAT_BIOLOGIQUE",
            "FINANCIER",
            "AUTHENTIFICATION_SECRET",
        ],
        "chiffrement": "TLS ; certificat d'une autorité interne Caddy par défaut (`tls internal`).",
        "authentification": "JWT porteur, sauf sur les routes publiques recensées par le lot A.",
        "persistance": "aucune côté proxy.",
        "journalisation": (
            "AUCUN journal d'accès : le Caddyfile ne contient pas de directive "
            "`log`. Aucune trace des accès externes n'est donc conservée au "
            "niveau du proxy."
        ),
        "activation_requise": "non",
        "risque_residuel": (
            "Certificat d'autorité interne : un poste sans la racine Caddy "
            "installée verra un avertissement, ce qui entraîne l'habitude de "
            "l'ignorer. Absence de journal d'accès : aucune investigation "
            "possible après incident au niveau du proxy."
        ),
    },
    {
        "id": "proxy_vers_application",
        "frontiere_lot_a": "Proxy → application",
        "origine": "proxy Caddy",
        "destination": "conteneur `app` (8000/TCP, réseau Docker interne)",
        "protocole": "HTTP en clair",
        "declencheur": "chaque requête relayée",
        "etat_par_defaut": "actif",
        "categories_donnees": [
            "IDENTITE",
            "DONNEE_DE_SANTE",
            "RESULTAT_BIOLOGIQUE",
            "FINANCIER",
            "AUTHENTIFICATION_SECRET",
        ],
        "chiffrement": "aucun — HTTP en clair sur le réseau Docker.",
        "authentification": "aucune entre les deux conteneurs ; l'application se fie à `X-Forwarded-For`.",
        "persistance": "aucune.",
        "journalisation": "journal applicatif structuré (chemin, méthode, code, durée, IP cliente).",
        "activation_requise": "non",
        "risque_residuel": (
            "Un conteneur compromis sur le même réseau Docker lit le trafic en "
            "clair, jetons compris, et peut se présenter directement à `app:8000` "
            "en contournant le proxy — donc les blocages §14 (/metrics, /docs)."
        ),
    },
    {
        "id": "application_vers_postgresql",
        "frontiere_lot_a": "Application → PostgreSQL",
        "origine": "conteneur `app`, `scheduler`, `analyzer-gateway`, `migrate`",
        "destination": "conteneur `db` (5432/TCP, réseau interne)",
        "protocole": "protocole PostgreSQL",
        "declencheur": "chaque requête applicative",
        "etat_par_defaut": "actif",
        "categories_donnees": ["TOUTES"],
        "chiffrement": "aucun TLS observé sur la connexion base.",
        "authentification": "mot de passe applicatif issu de l'environnement.",
        "persistance": "volume Docker, non chiffré.",
        "journalisation": "journaux PostgreSQL par défaut de l'image ; aucune journalisation d'audit SQL activée.",
        "activation_requise": "non",
        "risque_residuel": (
            "Un compte unique porte tous les droits applicatifs : aucune "
            "politique RLS n'existe (zéro relevée par le lot A), donc le "
            "cloisonnement par unité vit entièrement dans le code applicatif. "
            "Un accès direct à la base l'ignore intégralement."
        ),
    },
    {
        "id": "application_vers_valkey",
        "frontiere_lot_a": "Application → Valkey (cache)",
        "origine": "conteneur `app`",
        "destination": "conteneur Valkey (6379/TCP, réseau interne)",
        "protocole": "RESP",
        "declencheur": "cache, limitation de débit, quotas, file de trames brutes.",
        "etat_par_defaut": "actif quand CACHE_BACKEND=redis ; mémoire locale sinon.",
        "categories_donnees": ["TECHNIQUE", "A_QUALIFIER"],
        "chiffrement": "aucun.",
        "authentification": "selon la configuration du déploiement.",
        "persistance": "selon l'image ; la file de trames brutes est bornée par LTRIM.",
        "journalisation": "aucune journalisation applicative du contenu mis en cache.",
        "activation_requise": "non",
        "risque_residuel": (
            "Le contenu réellement mis en cache n'a pas été inventorié champ par "
            "champ : classé A_QUALIFIER, non NON_SENSIBLE."
        ),
    },
    {
        "id": "sauvegardes",
        "frontiere_lot_a": "Sauvegardes",
        "origine": "service `db-backup`",
        "destination": "volume de sauvegarde local",
        "protocole": "pg_dump, format custom",
        "declencheur": "planification du service",
        "etat_par_defaut": "actif",
        "categories_donnees": ["TOUTES"],
        "chiffrement": "aucun — le dump n'est pas chiffré.",
        "authentification": "compte PostgreSQL applicatif.",
        "persistance": "volume local ; aucune copie hors site prévue par la stack.",
        "journalisation": "somme SHA-256 du dump vérifiée en CI.",
        "activation_requise": "non",
        "risque_residuel": (
            "Une copie complète et non chiffrée de toute la base — identités, "
            "résultats, sérologies — repose sur le même hôte. Quiconque accède "
            "au volume dispose de l'intégralité des données, sans passer par "
            "aucune garde applicative."
        ),
    },
    {
        "id": "exports_csv_pdf",
        "frontiere_lot_a": "Exports CSV / PDF",
        "origine": "application",
        "destination": "poste de l'utilisateur (téléchargement)",
        "protocole": "HTTPS via le proxy",
        "declencheur": "action explicite d'un utilisateur authentifié",
        "etat_par_defaut": "actif",
        "categories_donnees": [
            "IDENTITE",
            "DONNEE_DE_SANTE",
            "RESULTAT_BIOLOGIQUE",
            "FINANCIER",
            "AUDIT",
        ],
        "chiffrement": "TLS en transit ; le fichier déposé sur le poste n'est pas chiffré.",
        "authentification": "garde de la route d'export.",
        "persistance": "hors du périmètre du système dès le téléchargement.",
        "journalisation": "requête tracée dans le journal applicatif ; aucun audit métier d'export observé sur toutes les routes d'export.",
        "activation_requise": "non",
        "risque_residuel": (
            "Le système perd la maîtrise de la donnée à l'instant du "
            "téléchargement. Aucun filigrane, aucun marquage de destinataire, "
            "et pas d'enregistrement d'audit systématique de l'export."
        ),
    },
    {
        "id": "impression",
        "frontiere_lot_a": "Imprimante",
        "origine": "navigateur du poste client",
        "destination": "imprimante du service",
        "protocole": "impression navigateur — non instrumentée",
        "declencheur": "action de l'utilisateur",
        "etat_par_defaut": "actif, hors instrumentation",
        "categories_donnees": ["IDENTITE", "RESULTAT_BIOLOGIQUE", "FINANCIER"],
        "chiffrement": "sans objet.",
        "authentification": "aucune — l'application ne voit pas l'impression.",
        "persistance": "papier.",
        "journalisation": "aucune : l'application ne peut pas savoir qu'un document a été imprimé.",
        "activation_requise": "non",
        "risque_residuel": (
            "Angle mort complet de la traçabilité : un compte rendu imprimé "
            "quitte le système sans laisser de trace exploitable."
        ),
    },
    {
        "id": "journaux",
        "frontiere_lot_a": "Journaux applicatifs",
        "origine": "conteneurs `app`, `scheduler`, `analyzer-gateway`",
        "destination": "sortie standard, collectée par le pilote de journalisation Docker",
        "protocole": "JSON structuré sur stdout",
        "declencheur": "chaque requête et chaque erreur",
        "etat_par_defaut": "actif",
        "categories_donnees": ["TECHNIQUE", "A_QUALIFIER"],
        "chiffrement": "aucun.",
        "authentification": "aucune — quiconque lit les journaux du conteneur lit tout.",
        "persistance": "selon le pilote Docker de l'hôte ; aucune rotation définie par la stack.",
        "journalisation": "sans objet.",
        "activation_requise": "non",
        "risque_residuel": (
            "Le chemin de requête est journalisé tel quel. Les identifiants "
            "d'objet y figurent, et le jeton de vérification d'un compte rendu "
            "en fait partie puisqu'il est porté par l'URL. Mesuré par la sonde "
            "sentinelle, voir `log-sentinel-observations.json`."
        ),
    },
    {
        "id": "prometheus",
        "frontiere_lot_a": "Prometheus",
        "origine": "Prometheus",
        "destination": "`app:8000/metrics` par le réseau interne",
        "protocole": "HTTP en clair",
        "declencheur": "collecte périodique",
        "etat_par_defaut": "actif ; `/metrics` renvoyé en 404 par le proxy (§14).",
        "categories_donnees": ["TECHNIQUE"],
        "chiffrement": "aucun.",
        "authentification": "aucune sur `/metrics`.",
        "persistance": "base de séries temporelles Prometheus.",
        "journalisation": "sans objet.",
        "activation_requise": "non",
        "risque_residuel": (
            "L'étiquette `endpoint` porte le gabarit de route, pas le chemin "
            "concret : aucun identifiant patient ne devient une étiquette. "
            "Vérifié par la sonde sentinelle. Le point reste joignable sans "
            "authentification depuis le réseau interne."
        ),
    },
    {
        "id": "grafana",
        "frontiere_lot_a": "Grafana (overlay optionnel)",
        "origine": "Grafana",
        "destination": "Prometheus",
        "protocole": "HTTP interne",
        "declencheur": "consultation d'un tableau de bord",
        "etat_par_defaut": "absent du cœur — overlay optionnel, jamais démarré par `docker-compose.yml`.",
        "categories_donnees": ["TECHNIQUE"],
        "chiffrement": "aucun.",
        "authentification": "identifiants d'administration Grafana fournis par l'environnement.",
        "persistance": "volume Grafana.",
        "journalisation": "journaux Grafana.",
        "activation_requise": "oui — overlay explicite.",
        "risque_residuel": "Composant tiers hors du périmètre distribué ; non audité par cette baseline.",
    },
    {
        "id": "csa_supabase",
        "frontiere_lot_a": "CSA / Supabase",
        "origine": "application",
        "destination": "plateforme CSA (Supabase, Internet)",
        "protocole": "HTTPS",
        "declencheur": "synchronisation entrante des prescriptions, sortante des résultats validés",
        "etat_par_defaut": "DESACTIVEE — CSA_SYNC_ENABLED=false",
        "categories_donnees": ["IDENTITE", "DONNEE_DE_SANTE", "RESULTAT_BIOLOGIQUE"],
        "chiffrement": "TLS.",
        "authentification": "compte technique dédié côté CSA.",
        "persistance": "csa_sync_state pour l'état ; les objets métier suivent leur table.",
        "journalisation": "csa_sync_state.last_error / last_outbound_error.",
        "activation_requise": "oui",
        "risque_residuel": (
            "Frontière la plus lourde du système : elle ferait sortir identités "
            "et résultats vers une plateforme tierce. Elle est coupée par "
            "configuration, et cette baseline ne l'active pas."
        ),
    },
    {
        "id": "onmci",
        "frontiere_lot_a": "ONMCI",
        "origine": "application",
        "destination": "point de notification ONMCI",
        "protocole": "HTTPS",
        "declencheur": "transmission d'une notification épidémiologique",
        "etat_par_defaut": "fail-closed — refuse de transmettre si la configuration est absente.",
        "categories_donnees": ["IDENTITE", "DONNEE_DE_SANTE"],
        "chiffrement": "TLS.",
        "authentification": "selon la configuration du client ONMCI.",
        "persistance": "epi_notifications.notified_at.",
        "journalisation": "audit_events sur transmission.",
        "activation_requise": "oui",
        "risque_residuel": "Sortie de données nominatives de santé vers un tiers institutionnel.",
    },
    {
        "id": "webhooks_sortants",
        "frontiere_lot_a": "Webhooks sortants",
        "origine": "application (alertes critiques, péremptions, stock)",
        "destination": "URL configurée dans notif_configs.webhook_url",
        "protocole": "HTTPS",
        "declencheur": "alerte déclenchée",
        "etat_par_defaut": "selon configuration ; aucune URL par défaut.",
        "categories_donnees": ["A_QUALIFIER", "RESULTAT_BIOLOGIQUE"],
        "chiffrement": "TLS.",
        "authentification": "portée par l'URL elle-même le cas échéant.",
        "persistance": "aucune côté application.",
        "journalisation": "journal applicatif.",
        "activation_requise": "oui",
        "risque_residuel": (
            "L'URL de destination est choisie par un utilisateur autorisé : "
            "c'est une sortie de données pilotée par la configuration. Un "
            "transport centralisé anti-SSRF existe ; le contenu réellement "
            "transmis par chaque notificateur n'a pas été inventorié champ par "
            "champ dans cette baseline."
        ),
    },
    {
        "id": "cdn_navigateur",
        "frontiere_lot_a": "Navigateur → CDN (Leaflet, JsBarcode)",
        "origine": "navigateur du poste client",
        "destination": "CDN publics sur Internet",
        "protocole": "HTTPS",
        "declencheur": "chargement d'une page du cockpit",
        "etat_par_defaut": "actif",
        "categories_donnees": [
            "AUCUNE donnée applicative ne part — seule la requête de ressource."
        ],
        "chiffrement": "TLS.",
        "authentification": "aucune.",
        "persistance": "cache du navigateur.",
        "journalisation": "journaux du CDN, hors du système.",
        "activation_requise": "non",
        "risque_residuel": (
            "Dépendance d'exécution à un tiers depuis le poste client : sur un "
            "LAN sans Internet, la ressource ne charge pas ; avec Internet, le "
            "CDN apprend l'existence et l'horaire d'usage de l'application. "
            "Le code exécuté dans le navigateur vient d'un tiers."
        ),
    },
    {
        "id": "tuiles_osm",
        "frontiere_lot_a": "Navigateur → tuiles OpenStreetMap",
        "origine": "navigateur du poste client, page `/app/map`",
        "destination": "serveurs de tuiles OpenStreetMap",
        "protocole": "HTTPS",
        "declencheur": "affichage de la cartographie",
        "etat_par_defaut": "actif",
        "categories_donnees": ["OPERATIONNEL_MILITAIRE (indirect : la zone consultée)"],
        "chiffrement": "TLS.",
        "authentification": "aucune.",
        "persistance": "cache du navigateur.",
        "journalisation": "journaux du fournisseur de tuiles, hors du système.",
        "activation_requise": "non",
        "risque_residuel": (
            "Les coordonnées demandées révèlent au fournisseur de tuiles les "
            "zones consultées sur une carte d'établissements militaires. "
            "À qualifier par l'autorité compétente."
        ),
    },
    {
        "id": "automates_desactives",
        "frontiere_lot_a": "Automate DH36 et trames brutes (TCP entrant)",
        "origine": "automate de laboratoire sur le réseau local",
        "destination": "`analyzer-gateway`",
        "protocole": "TCP",
        "declencheur": "émission d'une trame par l'automate",
        "etat_par_defaut": "DESACTIVES — ENABLE_DH36_LISTENER=false, ANALYZER_RAW_LISTENER_ENABLED=false",
        "categories_donnees": ["RESULTAT_BIOLOGIQUE", "TECHNIQUE"],
        "chiffrement": "aucun — protocole d'automate en clair.",
        "authentification": (
            "aucune au niveau TCP ; l'écoute est bornée par ANALYZER_BIND_IP, "
            "et le démarrage est refusé sur 0.0.0.0."
        ),
        "persistance": "dh36_inbound_messages (trame brute conservée).",
        "journalisation": "journal de la passerelle.",
        "activation_requise": "oui",
        "risque_residuel": (
            "Si activée, une frontière TCP non authentifiée et non chiffrée "
            "reçoit des résultats et les stocke en trame brute. Coupée par "
            "défaut, et cette baseline ne l'active pas."
        ),
    },
    {
        "id": "registres_paquets",
        "frontiere_lot_a": "Registres logiciels (build)",
        "origine": "runner de construction",
        "destination": "PyPI, Docker Hub, GHCR",
        "protocole": "HTTPS",
        "declencheur": "construction de l'image",
        "etat_par_defaut": "actif au build uniquement ; jamais à l'exécution.",
        "categories_donnees": ["AUCUNE donnée applicative."],
        "chiffrement": "TLS.",
        "authentification": "jeton du runner pour GHCR.",
        "persistance": "image candidate, artefact interne de la CI.",
        "journalisation": "journaux de la CI.",
        "activation_requise": "non",
        "risque_residuel": (
            "Chaîne d'approvisionnement : le contenu de l'image dépend de tiers. "
            "Atténué par l'épinglage des actions par SHA et par les SBOM produits "
            "par le job de conformité de licences."
        ),
    },
)

# ── 6. Revue de `.secrets.baseline` ─────────────────────────────────────────
#
# Un jugement par emplacement. Aucune valeur, aucun fragment de valeur : une
# valeur tronquée reste un indice exploitable.
#
# `caractere` ∈ {FACTICE_DE_TEST, EXEMPLE_DOCUMENTAIRE, FAUX_POSITIF,
#                SECRET_DE_CI_NON_PRODUCTION, SECRET_REEL}
# Une seule occurrence de SECRET_REEL arrête le lot et déclenche un P0.
REVUE_BASELINE_SECRETS: dict[str, dict[str, Any]] = {
    ".env.example": {
        "caractere": "EXEMPLE_DOCUMENTAIRE",
        "statut": "ACCEPTE",
        "justification": (
            "Fichier d'exemple, versionné pour être copié en `.env`. Les valeurs "
            "sont des marque-place destinés à être remplacés au déploiement ; "
            "aucune ne donne accès à quoi que ce soit."
        ),
        "rotation_necessaire": False,
    },
    ".github/workflows/ci.yml": {
        "caractere": "SECRET_DE_CI_NON_PRODUCTION",
        "statut": "ACCEPTE",
        "justification": (
            "Identifiants de bases jetables créées et détruites dans le runner, "
            "écrits en clair pour que le pipeline soit rejouable. Ils ne "
            "désignent aucun système durable et ne survivent pas au job."
        ),
        "rotation_necessaire": False,
    },
    "docs/SECRETS_MANAGEMENT.md": {
        "caractere": "EXEMPLE_DOCUMENTAIRE",
        "statut": "ACCEPTE",
        "justification": (
            "Documentation de la gestion des secrets : les valeurs citées "
            "illustrent un format, elles ne sont utilisées nulle part."
        ),
        "rotation_necessaire": False,
    },
    "scripts/check_pw.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Utilitaire local de vérification, valeur d'essai sans portée.",
        "rotation_necessaire": False,
    },
    "scripts/verify_db_password.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Utilitaire local de vérification, valeur d'essai sans portée.",
        "rotation_necessaire": False,
    },
    "tests/conftest.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Amorçage de la base SQLite de test, détruite à la fin de chaque test.",
        "rotation_necessaire": False,
    },
    "tests/test_api.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Identifiants de comptes créés puis détruits par le test.",
        "rotation_necessaire": False,
    },
    "tests/test_auth_refresh.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Identifiants de comptes créés puis détruits par le test.",
        "rotation_necessaire": False,
    },
    "tests/test_fhir_export.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Identifiants de comptes créés puis détruits par le test.",
        "rotation_necessaire": False,
    },
    "tests/test_login_security.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": (
            "Le test porte sur le durcissement de la connexion : il lui faut des "
            "mots de passe littéraux, y compris volontairement faibles."
        ),
        "rotation_necessaire": False,
    },
    "tests/test_rate_limiting.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Identifiants d'essai pour éprouver la limitation de débit.",
        "rotation_necessaire": False,
    },
    "tests/test_security.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Valeur littérale nécessaire au test de hachage.",
        "rotation_necessaire": False,
    },
    "tests/test_stock_notifications.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Identifiants de comptes créés puis détruits par le test.",
        "rotation_necessaire": False,
    },
    "tests/test_token_cleanup.py": {
        "caractere": "FACTICE_DE_TEST",
        "statut": "ACCEPTE",
        "justification": "Identifiants de comptes créés puis détruits par le test.",
        "rotation_necessaire": False,
    },
}
