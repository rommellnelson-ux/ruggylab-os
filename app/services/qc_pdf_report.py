"""Service — Rapport QC mensuel (HTML imprimable + SVG Levey-Jennings).

Génère un document HTML standalone, auto-suffisant (CSS inline, SVG inline),
conçu pour l'impression A4 et l'export PDF via le navigateur.
Aucune dépendance externe — stdlib Python uniquement.
"""

from __future__ import annotations

import datetime as dt
import json
import math

from sqlalchemy.orm import Session

from app.models import QcControl, QcResult
from app.schemas.qc import QC_REJECT_RULES

_MONTH_NAMES = [
    "",
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
]


# ──────────────────────────────────────────────────────────────────────────────
#  SVG Levey-Jennings (server-side)
# ──────────────────────────────────────────────────────────────────────────────


def _lj_svg(values: list[float], mean: float, sd: float, dates: list[str]) -> str:
    width, height = 600, 180
    margin_left, margin_right, margin_top, margin_bottom = 46, 16, 16, 28
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    n = len(values)
    if n == 0 or sd <= 0:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'style="border:1px solid #e5e7eb;border-radius:4px;">'
            f'<text x="50%" y="50%" text-anchor="middle" fill="#9ca3af" font-size="12">'
            f"Aucune donnée</text></svg>"
        )

    z_scores = [(v - mean) / sd for v in values]
    y_min, y_max = -3.6, 3.6
    y_range = y_max - y_min

    def px(i: int) -> float:
        return margin_left + (i / max(n - 1, 1)) * plot_width

    def py(z: float) -> float:
        return margin_top + (1.0 - (z - y_min) / y_range) * plot_height

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'style="border:1px solid #e5e7eb;border-radius:4px;background:#fafafa;">'
    )

    # Bands
    bands = [
        (-1, 1, "#fef9c3"),
        (-2, -1, "#fed7aa"),
        (1, 2, "#fed7aa"),
        (-3, -2, "#fecaca"),
        (2, 3, "#fecaca"),
    ]
    for zlo, zhi, fill in bands:
        ytop = py(zhi)
        ybot = py(zlo)
        parts.append(
            f'<rect x="{margin_left}" y="{ytop:.1f}" width="{plot_width}" '
            f'height="{ybot - ytop:.1f}" fill="{fill}" opacity="0.55"/>'
        )

    # Reference lines
    ref_lines = [
        (0, "#374151", 1.4, "none"),
        (1, "#ca8a04", 0.6, "4 2"),
        (-1, "#ca8a04", 0.6, "4 2"),
        (2, "#ea580c", 0.6, "4 2"),
        (-2, "#ea580c", 0.6, "4 2"),
        (3, "#dc2626", 0.6, "4 2"),
        (-3, "#dc2626", 0.6, "4 2"),
    ]
    for z, stroke, sw, dash in ref_lines:
        y = py(z)
        da = f' stroke-dasharray="{dash}"' if dash != "none" else ""
        parts.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{margin_left + plot_width}" y2="{y:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw}"{da}/>'
        )
        lbl = f"{z:+.0f}σ"
        parts.append(
            f'<text x="{margin_left - 3}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="8" fill="{stroke}">{lbl}</text>'
        )

    # Data polyline
    if n > 1:
        pts = " ".join(f"{px(i):.1f},{py(z):.1f}" for i, z in enumerate(z_scores))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="1.5"/>')

    # Data points
    for i, (z, v) in enumerate(zip(z_scores, values, strict=True)):
        col = "#dc2626" if abs(z) > 3 else "#ea580c" if abs(z) > 2 else "#2563eb"
        x, y = px(i), py(z)
        tooltip = f"{dates[i]}: {v:.3f}"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{col}" '
            f'stroke="white" stroke-width="1"><title>{tooltip}</title></circle>'
        )

    # X-axis labels (max 10)
    step = max(1, n // 10)
    for i in range(0, n, step):
        x = px(i)
        lbl = dates[i][-5:] if len(dates[i]) >= 5 else dates[i]
        parts.append(
            f'<text x="{x:.1f}" y="{height - 4}" text-anchor="middle" '
            f'font-size="8" fill="#6b7280">{lbl}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
#  HTML report builder
# ──────────────────────────────────────────────────────────────────────────────


def _status_badge(status: str) -> str:
    mapping = {
        "ok": ('<span style="color:#16a34a;font-weight:600;">✓ OK</span>'),
        "warn": ('<span style="color:#ca8a04;font-weight:600;">⚠ Alerte 1-2s</span>'),
        "reject": ('<span style="color:#dc2626;font-weight:600;">⛔ Rejet</span>'),
        "no_data": ('<span style="color:#9ca3af;">— Aucune donnée</span>'),
    }
    return mapping.get(status, status)


def build_qc_html_report(year: int, month: int, db: Session) -> str:
    """Génère un rapport QC HTML imprimable pour le mois donné."""
    generated_at = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    month_name = _MONTH_NAMES[month]

    from_date = dt.date(year, month, 1)
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    to_date = dt.date(next_year, next_month, 1)

    controls = (
        db.query(QcControl)
        .filter(QcControl.is_active.is_(True))
        .order_by(QcControl.analyte, QcControl.level)
        .all()
    )

    summary_rows_html = ""
    sections_html = ""

    for ctrl in controls:
        qc_results = (
            db.query(QcResult)
            .filter(
                QcResult.control_id == ctrl.id,
                QcResult.measured_at >= from_date,
                QcResult.measured_at < to_date,
            )
            .order_by(QcResult.measured_at)
            .all()
        )

        values = [r.value for r in qc_results]
        dates = [str(r.measured_at) for r in qc_results]
        n = len(values)

        # Statistiques observées
        if n > 0:
            obs_mean = sum(values) / n
            obs_sd = math.sqrt(sum((v - obs_mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
        else:
            obs_mean, obs_sd = 0.0, 0.0

        # Violations et statut
        reject_count = 0
        warn_count = 0
        all_viols: list[str] = []
        for r in qc_results:
            if not r.violations:
                continue
            try:
                viols = json.loads(r.violations)
            except (json.JSONDecodeError, TypeError):
                viols = []
            all_viols.extend(viols)
            if any(v in QC_REJECT_RULES for v in viols):
                reject_count += 1
            elif any(v == "1-2s" for v in viols):
                warn_count += 1

        if n == 0:
            status = "no_data"
        elif reject_count > 0:
            status = "reject"
        elif warn_count > 0:
            status = "warn"
        else:
            status = "ok"

        row_bg = "#fee2e2" if status == "reject" else "#fef3c7" if status == "warn" else "white"
        obs_mean_s = f"{obs_mean:.3f}" if n > 0 else "—"
        obs_sd_s = f"{obs_sd:.3f}" if n > 0 else "—"
        summary_rows_html += (
            f"<tr style='background:{row_bg};'>"
            f"<td>{ctrl.analyte}</td><td>{ctrl.level}</td>"
            f"<td style='text-align:center;'>{n}</td>"
            f"<td style='text-align:center;'>{ctrl.target_mean:.3f}</td>"
            f"<td style='text-align:center;'>{ctrl.target_sd:.3f}</td>"
            f"<td style='text-align:center;'>{obs_mean_s}</td>"
            f"<td style='text-align:center;'>{obs_sd_s}</td>"
            f"<td style='text-align:center;'>{reject_count}</td>"
            f"<td style='text-align:center;'>{warn_count}</td>"
            f"<td style='text-align:center;'>{_status_badge(status)}</td>"
            "</tr>"
        )

        # SVG chart
        svg = _lj_svg(values, ctrl.target_mean, ctrl.target_sd, dates)

        # Results detail table
        detail_rows = ""
        for r in qc_results:
            try:
                viols = json.loads(r.violations or "[]")
            except (json.JSONDecodeError, TypeError):
                viols = []
            is_reject = any(v in QC_REJECT_RULES for v in viols)
            is_warn = any(v == "1-2s" for v in viols) and not is_reject
            zbg = "#fee2e2" if is_reject else "#fef3c7" if is_warn else "white"
            z = (r.value - ctrl.target_mean) / ctrl.target_sd if ctrl.target_sd > 0 else 0
            detail_rows += (
                f"<tr style='background:{zbg};'>"
                f"<td>{r.measured_at}</td>"
                f"<td style='text-align:center;'>{r.value:.3f}</td>"
                f"<td style='text-align:center;'>{z:+.2f}</td>"
                f"<td>{', '.join(viols) or '—'}</td>"
                f"<td>{r.operator or '—'}</td>"
                "</tr>"
            )

        sections_html += f"""
        <div class="section" style="page-break-inside:avoid;margin-top:28px;">
          <h3 style="margin:0 0 8px;color:#1e3a5f;">{ctrl.analyte} — {ctrl.level}
            <small style="font-weight:normal;color:#6b7280;">(cible: {ctrl.target_mean} ± {ctrl.target_sd} {ctrl.unit})</small>
          </h3>
          {svg}
          {"<table class='detail'><thead><tr><th>Date</th><th>Valeur</th><th>Z-score</th><th>Violations</th><th>Opérateur</th></tr></thead><tbody>" + detail_rows + "</tbody></table>" if n > 0 else "<p style='color:#9ca3af;font-style:italic;'>Aucun résultat ce mois.</p>"}
        </div>
        """

    total_controls = len(controls)
    total_reject = sum(1 for row in summary_rows_html.split("<tr") if "fee2e2" in row)
    total_warn = sum(1 for row in summary_rows_html.split("<tr") if "fef3c7" in row)

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rapport QC — {month_name} {year}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #111; padding: 20px; }}
    h1 {{ font-size: 20px; color: #1e3a5f; margin-bottom: 4px; }}
    h2 {{ font-size: 14px; color: #374151; font-weight: normal; margin-bottom: 16px; }}
    h3 {{ font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 10.5px; }}
    th {{ background: #1e3a5f; color: white; padding: 6px 8px; text-align: left; }}
    td {{ border: 1px solid #d1d5db; padding: 5px 7px; }}
    tr:nth-child(even) {{ background: #f9fafb; }}
    .summary th, .summary td {{ text-align: center; }}
    .summary td:first-child, .summary td:nth-child(2) {{ text-align: left; }}
    table.detail th, table.detail td {{ text-align: center; }}
    table.detail td:first-child, table.detail td:last-child {{ text-align: left; }}
    .kpi {{ display: flex; gap: 16px; margin: 12px 0; flex-wrap: wrap; }}
    .kpi-card {{ border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px 16px; min-width: 130px; }}
    .kpi-card .val {{ font-size: 22px; font-weight: 700; color: #1e3a5f; }}
    .kpi-card .lbl {{ font-size: 10px; color: #6b7280; margin-top: 2px; }}
    .noprint {{ margin-bottom: 16px; }}
    @media print {{
      @page {{ size: A4; margin: 15mm 12mm; }}
      .noprint {{ display: none !important; }}
      body {{ padding: 0; }}
    }}
  </style>
</head>
<body>
  <div class="noprint">
    <button onclick="window.print()" style="padding:8px 20px;background:#1e3a5f;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;">
      🖨 Imprimer / Exporter PDF
    </button>
    <button onclick="window.close()" style="margin-left:8px;padding:8px 16px;background:#e5e7eb;border:none;border-radius:4px;cursor:pointer;font-size:13px;">
      ✕ Fermer
    </button>
  </div>

  <h1>🏥 RuggyLab OS — Rapport Contrôle Qualité Analytique</h1>
  <h2>Période : {month_name} {year} &nbsp;·&nbsp; Généré le {generated_at}</h2>

  <div class="kpi">
    <div class="kpi-card"><div class="val">{total_controls}</div><div class="lbl">Contrôles actifs</div></div>
    <div class="kpi-card" style="border-color:#fee2e2;"><div class="val" style="color:#dc2626;">{total_reject}</div><div class="lbl">Contrôles en rejet</div></div>
    <div class="kpi-card" style="border-color:#fef3c7;"><div class="val" style="color:#ca8a04;">{total_warn}</div><div class="lbl">Contrôles en alerte</div></div>
  </div>

  <h3 style="margin-top:16px;color:#1e3a5f;">Résumé mensuel</h3>
  <table class="summary">
    <thead>
      <tr>
        <th>Analyte</th><th>Niveau</th><th>N mesures</th>
        <th>Cible µ</th><th>Cible σ</th>
        <th>µ observé</th><th>σ observé</th>
        <th>Rejets</th><th>Alertes</th><th>Statut</th>
      </tr>
    </thead>
    <tbody>{summary_rows_html}</tbody>
  </table>

  {sections_html}

  <hr style="margin-top:32px;border:none;border-top:1px solid #e5e7eb;">
  <p style="margin-top:8px;color:#9ca3af;font-size:9px;">
    RuggyLab OS · ISO 15189 · Rapport auto-généré · {generated_at}
  </p>
</body>
</html>"""

    return html
