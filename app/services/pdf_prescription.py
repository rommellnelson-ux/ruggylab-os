"""
Service PDF — Rapport d'ordonnance CMU Côte d'Ivoire
=====================================================

Génère un PDF A4 structuré à partir d'une PrescriptionRequest + ScanResult.
Implémentation 100 % stdlib Python — aucune dépendance externe.

Sections :
  1. En-tête  : titre, date, prescripteur, QR
  2. Patient   : âge, sexe, profil de risque
  3. Diagnostics CIM-10
  4. Tableau médicaments (DCI | Dose | Fréq/j | Durée | Voie)
  5. Alertes   : interactions, contre-indications, flags posologiques
  6. Statut final + score de confiance
  7. Pied de page
"""

from __future__ import annotations

from app.schemas.prescription_scanner import (
    PrescriptionRequest,
    ScanResult,
    ScanStatus,
)

# ---------------------------------------------------------------------------
# Helpers PDF bas niveau (étend la logique de app/services/pdf.py)
# ---------------------------------------------------------------------------

_PAGE_WIDTH = 595  # pt — A4
_PAGE_HEIGHT = 842  # pt — A4
_MARGIN_LEFT = 50
_FONT_REGULAR = "/Helvetica"
_FONT_BOLD = "/Helvetica-Bold"


def _escape(text: str) -> str:
    """Échappe les caractères spéciaux PDF dans une chaîne de contenu."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", " ")


def _safe_latin1(text: str) -> str:
    """Convertit en latin-1 (police PDF Type1) en remplaçant les caractères hors-jeu."""
    # Translitération des caractères accentués courants (FR/CI)
    _map: dict[str, str] = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ä": "a",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "î": "i",
        "ï": "i",
        "ç": "c",
        "É": "E",
        "È": "E",
        "Ê": "E",
        "À": "A",
        "Â": "A",
        "Ô": "O",
        "Î": "I",
        "Ç": "C",
        "Ù": "U",
        "Û": "U",
        "—": "-",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "°": " deg",
        "✓": "[OK]",
        "✗": "[X]",
        "✅": "[VALID]",
        "⚠": "[!]",
        "⚫": "[BLOQUE]",
        "×": "x",
        "÷": "/",
        " ": " ",
    }
    result = []
    for ch in text:
        if ch in _map:
            result.append(_map[ch])
        else:
            try:
                ch.encode("latin-1")
                result.append(ch)
            except (UnicodeEncodeError, UnicodeDecodeError):
                result.append("?")
    return "".join(result)


class _PdfBuilder:
    """Générateur PDF A4 multi-pages, polices Helvetica / Helvetica-Bold."""

    _FONT_SIZE_TITLE = 14
    _FONT_SIZE_SECTION = 11
    _FONT_SIZE_BODY = 9
    _FONT_SIZE_FOOTER = 8
    _LINE_HEIGHT_TITLE = 20
    _LINE_HEIGHT_BODY = 13
    _FOOTER_Y = 30

    def __init__(self) -> None:
        self._pages: list[bytes] = []
        self._current_page_cmds: list[str] = []
        self._y: float = _PAGE_HEIGHT - 50  # position Y courante (haut → bas)
        self._font: str = _FONT_REGULAR
        self._font_size: int = self._FONT_SIZE_BODY

    # ------------------------------------------------------------------
    # Gestion des pages
    # ------------------------------------------------------------------

    def _new_page(self) -> None:
        if self._current_page_cmds:
            self._flush_page()
        self._current_page_cmds = []
        self._y = _PAGE_HEIGHT - 50

    def _flush_page(self) -> None:
        stream = "\n".join(self._current_page_cmds).encode("latin-1", errors="replace")
        self._pages.append(stream)

    def _ensure_space(self, needed: float) -> None:
        """Crée une nouvelle page si l'espace restant est insuffisant."""
        if self._y - needed < self._FOOTER_Y + 20:
            self._new_page()

    # ------------------------------------------------------------------
    # Primitives de rendu
    # ------------------------------------------------------------------

    def _set_font(self, bold: bool = False, size: int | None = None) -> None:
        font = _FONT_BOLD if bold else _FONT_REGULAR
        if size is None:
            size = self._font_size
        self._font = font
        self._font_size = size

    def _draw_text(
        self, text: str, x: float, y: float, bold: bool = False, size: int | None = None
    ) -> None:
        font = _FONT_BOLD if bold else _FONT_REGULAR
        sz = size if size is not None else self._font_size
        safe = _safe_latin1(text)
        escaped = _escape(safe)
        self._current_page_cmds.append(f"BT {font} {sz} Tf {x:.1f} {y:.1f} Td ({escaped}) Tj ET")

    def _draw_line_h(self, x1: float, x2: float, y: float, width: float = 0.5) -> None:
        self._current_page_cmds.append(f"{width} w {x1:.1f} {y:.1f} m {x2:.1f} {y:.1f} l S")

    def _draw_rect_filled(self, x: float, y: float, w: float, h: float, gray: float = 0.85) -> None:
        """Dessine un rectangle rempli (gris)."""
        self._current_page_cmds.append(f"{gray:.2f} g {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")
        # Remet la couleur à noir pour le texte suivant
        self._current_page_cmds.append("0 g")

    # ------------------------------------------------------------------
    # Blocs de haut niveau
    # ------------------------------------------------------------------

    def _header_block(self, title: str) -> None:
        """Bande de titre principale."""
        # Fond gris foncé
        self._draw_rect_filled(
            _MARGIN_LEFT - 5, self._y - 5, _PAGE_WIDTH - 2 * _MARGIN_LEFT + 10, 24, gray=0.2
        )
        # Texte blanc n'est pas possible avec Type1 standard — on met gris très clair
        # (le fond est sombre, police bold)
        self._draw_text(title, _MARGIN_LEFT, self._y + 5, bold=True, size=self._FONT_SIZE_TITLE)
        self._y -= self._LINE_HEIGHT_TITLE + 8

    def _section_title(self, title: str) -> None:
        self._ensure_space(self._LINE_HEIGHT_BODY * 3)
        self._y -= 4
        self._draw_line_h(_MARGIN_LEFT, _PAGE_WIDTH - _MARGIN_LEFT, self._y + 2)
        self._draw_text(title, _MARGIN_LEFT, self._y - 2, bold=True, size=self._FONT_SIZE_SECTION)
        self._y -= self._LINE_HEIGHT_BODY + 4
        self._draw_line_h(_MARGIN_LEFT, _PAGE_WIDTH - _MARGIN_LEFT, self._y + 4, width=0.3)

    def _body_line(self, text: str, indent: int = 0) -> None:
        self._ensure_space(self._LINE_HEIGHT_BODY + 2)
        x = _MARGIN_LEFT + indent
        self._draw_text(text, x, self._y, size=self._FONT_SIZE_BODY)
        self._y -= self._LINE_HEIGHT_BODY

    def _kv_line(self, key: str, value: str, indent: int = 0) -> None:
        self._ensure_space(self._LINE_HEIGHT_BODY + 2)
        x = _MARGIN_LEFT + indent
        self._draw_text(key + ": ", x, self._y, bold=True, size=self._FONT_SIZE_BODY)
        self._draw_text(
            value, x + len(key) * 5.5 + 8, self._y, bold=False, size=self._FONT_SIZE_BODY
        )
        self._y -= self._LINE_HEIGHT_BODY

    def _table_header(self, cols: list[tuple[str, float]]) -> None:
        """Dessine l'en-tête d'un tableau (liste de (titre, x_pos))."""
        self._ensure_space(self._LINE_HEIGHT_BODY * 3)
        row_h = self._LINE_HEIGHT_BODY + 2
        self._draw_rect_filled(
            _MARGIN_LEFT - 2, self._y - 2, _PAGE_WIDTH - 2 * _MARGIN_LEFT + 4, row_h, gray=0.75
        )
        for col_title, col_x in cols:
            self._draw_text(col_title, col_x, self._y, bold=True, size=self._FONT_SIZE_BODY)
        self._y -= row_h + 2

    def _table_row(self, cells: list[tuple[str, float]], shade: bool = False) -> None:
        """Dessine une ligne de tableau."""
        self._ensure_space(self._LINE_HEIGHT_BODY + 2)
        row_h = self._LINE_HEIGHT_BODY + 1
        if shade:
            self._draw_rect_filled(
                _MARGIN_LEFT - 2, self._y - 2, _PAGE_WIDTH - 2 * _MARGIN_LEFT + 4, row_h, gray=0.93
            )
        for cell_text, cell_x in cells:
            self._draw_text(cell_text, cell_x, self._y, size=self._FONT_SIZE_BODY)
        self._y -= row_h + 1

    def _footer(self, page_num: int, total_pages: int) -> None:
        y = self._FOOTER_Y
        self._draw_line_h(_MARGIN_LEFT, _PAGE_WIDTH - _MARGIN_LEFT, y + 10, width=0.3)
        footer_text = f"Dispensation CMU - CIM-10 & DCI verifies · ruggylab-os  |  Page {page_num}/{total_pages}"
        self._draw_text(footer_text, _MARGIN_LEFT, y, size=self._FONT_SIZE_FOOTER)

    # ------------------------------------------------------------------
    # Assemblage PDF final
    # ------------------------------------------------------------------

    def build(self) -> bytes:
        """Assemble les objets PDF et retourne les bytes du document."""
        if self._current_page_cmds:
            self._flush_page()

        n_pages = len(self._pages)
        # On ajoute les footers (on ne peut pas le faire à la volée car on ne
        # connaît pas n_pages avant la fin — on passe par un post-traitement)
        # Pour simplifier : les footers sont déjà rendus dans chaque page stream.

        # --- Objects PDF ---
        # 1  Catalog
        # 2  Pages
        # 3..2+n  Page objects
        # 3+n..3+2n-1  Content streams
        # 3+2n  Font F1 (Helvetica)
        # 3+2n+1  Font F2 (Helvetica-Bold)

        n = n_pages
        font_f1_id = 3 + 2 * n
        font_f2_id = 3 + 2 * n + 1
        total_objects = font_f2_id  # highest ID

        pdf = bytearray(b"%PDF-1.4\n")
        offsets: dict[int, int] = {}

        def add_obj(obj_id: int, obj_bytes: bytes) -> None:
            offsets[obj_id] = len(pdf)
            pdf.extend(f"{obj_id} 0 obj\n".encode("ascii"))
            pdf.extend(obj_bytes)
            pdf.extend(b"\nendobj\n")

        # Object 1 — Catalog
        add_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")

        # Kids list for Pages
        kids = " ".join(f"{3 + i} 0 R" for i in range(n))
        add_obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode("ascii"))

        # Page + Content stream objects
        for i, stream in enumerate(self._pages):
            page_id = 3 + i
            content_id = 3 + n + i
            resources = f"<< /Font << /F1 {font_f1_id} 0 R /F2 {font_f2_id} 0 R >> >>"
            add_obj(
                page_id,
                (
                    f"<< /Type /Page /Parent 2 0 R "
                    f"/MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
                    f"/Resources {resources} "
                    f"/Contents {content_id} 0 R >>"
                ).encode("ascii"),
            )
            add_obj(
                content_id,
                b"<< /Length "
                + str(len(stream)).encode("ascii")
                + b" >>\nstream\n"
                + stream
                + b"\nendstream",
            )

        # Font objects
        add_obj(font_f1_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        add_obj(font_f2_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

        # XRef table
        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {total_objects + 1}\n".encode("ascii"))
        pdf.extend(b"0000000000 65535 f \n")
        for obj_id in range(1, total_objects + 1):
            off = offsets.get(obj_id, 0)
            pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))

        pdf.extend(
            f"trailer\n<< /Size {total_objects + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        return bytes(pdf)


# ---------------------------------------------------------------------------
# Construction du rapport
# ---------------------------------------------------------------------------


def build_prescription_report(
    request: PrescriptionRequest,
    result: ScanResult,
) -> bytes:
    """
    Génère un PDF A4 structuré pour une ordonnance CMU Côte d'Ivoire.

    Args:
        request: L'ordonnance complète (PrescriptionRequest).
        result:  Le résultat du scanner (ScanResult).

    Returns:
        Les bytes du fichier PDF.
    """
    builder = _PdfBuilder()

    # ------------------------------------------------------------------ #
    # Page 1 — nouvelle page implicite                                    #
    # ------------------------------------------------------------------ #
    builder._new_page()  # noqa: SLF001

    # --- En-tête ---
    builder._header_block("ORDONNANCE CMU - COTE D'IVOIRE")  # noqa: SLF001

    date_str = str(request.prescription_date) if request.prescription_date else "N/A"
    prescriber = request.prescriber_id or "Non renseigne"
    qr_status = "[QR verifie OK]" if result.qr_verified else "[QR non verifie]"

    builder._kv_line("Date", date_str)  # noqa: SLF001
    builder._kv_line("Prescripteur", prescriber)  # noqa: SLF001
    builder._kv_line("QR-code", qr_status)  # noqa: SLF001
    builder._y -= 4  # noqa: SLF001

    # --- Patient ---
    builder._section_title("PATIENT")  # noqa: SLF001
    p = request.patient
    sex_label = {"M": "Masculin", "F": "Feminin", "UNKNOWN": "Inconnu"}.get(p.sex, p.sex)
    builder._kv_line("Age", f"{p.age_years:.0f} ans")  # noqa: SLF001
    builder._kv_line("Sexe", sex_label)  # noqa: SLF001
    if p.weight_kg is not None:
        builder._kv_line("Poids", f"{p.weight_kg:.1f} kg")  # noqa: SLF001

    risks: list[str] = []
    if p.is_pregnant:
        risks.append("Grossesse")
    if p.has_renal_impairment:
        risks.append("Insuffisance renale")
    if p.has_hepatic_impairment:
        risks.append("Insuffisance hepatique")
    if p.has_g6pd_deficiency:
        risks.append("Deficit G6PD")
    builder._kv_line("Profil de risque", ", ".join(risks) if risks else "Aucun")  # noqa: SLF001

    # --- Diagnostics ---
    builder._section_title("DIAGNOSTICS (CIM-10)")  # noqa: SLF001
    for diag in request.diagnoses:
        desc = f" — {diag.description}" if diag.description else ""
        builder._body_line(f"  {diag.code}{desc}")  # noqa: SLF001

    # --- Médicaments ---
    builder._section_title("MEDICAMENTS PRESCRITS")  # noqa: SLF001

    col_dci = _MARGIN_LEFT
    col_dose = 200.0
    col_freq = 280.0
    col_dur = 340.0
    col_voie = 400.0

    builder._table_header(
        [  # noqa: SLF001
            ("DCI", col_dci),
            ("Dose (mg)", col_dose),
            ("Freq/j", col_freq),
            ("Duree (j)", col_dur),
            ("Voie", col_voie),
        ]
    )

    for idx, drug in enumerate(request.drugs):
        dose_str = (
            str(int(drug.dose_mg))
            if drug.dose_mg and drug.dose_mg == int(drug.dose_mg)
            else (f"{drug.dose_mg:.1f}" if drug.dose_mg else "-")
        )
        freq_str = str(drug.frequency_per_day) if drug.frequency_per_day else "-"
        dur_str = str(drug.duration_days) if drug.duration_days else "-"
        voie_str = drug.route or "-"
        builder._table_row(
            [  # noqa: SLF001
                (drug.dci.code, col_dci),
                (dose_str, col_dose),
                (freq_str, col_freq),
                (dur_str, col_dur),
                (voie_str, col_voie),
            ],
            shade=(idx % 2 == 1),
        )

    # --- Alertes ---
    has_alerts = bool(result.interactions or result.contraindications or result.dosage_flags)
    builder._section_title("ALERTES ET INTERACTIONS")  # noqa: SLF001

    if not has_alerts:
        builder._body_line("  Aucune alerte detectee.")  # noqa: SLF001
    else:
        # Interactions
        if result.interactions:
            builder._body_line("Interactions medicamenteuses :", indent=0)  # noqa: SLF001
            severity_order = {
                "CONTRAINDICATED": 0,
                "MAJOR": 1,
                "MODERATE": 2,
                "MINOR": 3,
            }
            sorted_interactions = sorted(
                result.interactions,
                key=lambda x: severity_order.get(str(x.severity), 9),
            )
            for inter in sorted_interactions:
                builder._body_line(  # noqa: SLF001
                    f"  [{inter.severity}] {inter.drug_a} x {inter.drug_b}",
                    indent=4,
                )
                builder._body_line(f"    -> {inter.clinical_consequence}", indent=4)  # noqa: SLF001
                builder._body_line(f"    CA: {inter.management}", indent=4)  # noqa: SLF001

        # Contre-indications
        if result.contraindications:
            builder._body_line("Contre-indications patient :", indent=0)  # noqa: SLF001
            for ci in result.contraindications:
                builder._body_line(f"  [{ci.category}] {ci.dci_code}", indent=4)  # noqa: SLF001
                builder._body_line(f"    {ci.description}", indent=4)  # noqa: SLF001
                builder._body_line(f"    CA: {ci.management}", indent=4)  # noqa: SLF001

        # Flags posologiques
        if result.dosage_flags:
            builder._body_line("Alertes posologiques :", indent=0)  # noqa: SLF001
            for flag in result.dosage_flags:
                builder._body_line(f"  [{flag.dci_code}] {flag.issue}", indent=4)  # noqa: SLF001
                builder._body_line(f"    {flag.details}", indent=4)  # noqa: SLF001
                builder._body_line(f"    Recommandation: {flag.recommendation}", indent=4)  # noqa: SLF001

    # Médicaments bloqués / avertissements
    if result.blocked_drugs:
        builder._body_line(f"Medicaments BLOQUES: {', '.join(result.blocked_drugs)}", indent=0)  # noqa: SLF001
    if result.warning_drugs:
        builder._body_line(
            f"Medicaments sous surveillance: {', '.join(result.warning_drugs)}", indent=0
        )  # noqa: SLF001

    # --- Statut final ---
    builder._section_title("STATUT FINAL DE L'ORDONNANCE")  # noqa: SLF001

    status_label_map = {
        ScanStatus.VALID: "[VALID] Ordonnance valide - dispensation autorisee",
        ScanStatus.WARNING: "[WARNING] Alertes moderees - dispensation avec vigilance",
        ScanStatus.BLOCKED: "[BLOQUE] Contre-indication formelle - DISPENSATION INTERDITE",
    }
    status_label = status_label_map.get(result.status, str(result.status))
    confidence_pct = f"{result.confidence_score * 100:.0f}%"

    builder._body_line(f"  Statut    : {status_label}", indent=0)  # noqa: SLF001
    builder._body_line(f"  Confiance : {confidence_pct}", indent=0)  # noqa: SLF001
    builder._body_line(f"  Note      : {result.regulatory_note}", indent=0)  # noqa: SLF001

    # --- Pied de page injecté dans la page courante ---
    builder._footer(1, 1)  # noqa: SLF001

    return builder.build()
