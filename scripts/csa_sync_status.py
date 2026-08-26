"""Statut de l'intégration CSA (I4) — lecture seule, aucun appel réseau.

Affiche l'état des deux flux (entrant/sortant), la file de résultats en attente
de remontée, et les examens non mappés à curer dans exam_map. À lancer sur la
base RuggyLab (dev/staging/prod) :

    python scripts/csa_sync_status.py

N'ouvre pas de connexion à CSA : lit uniquement la base RuggyLab.
"""

from __future__ import annotations

import json
import sys

from app.db.session import SessionLocal
from app.services.csa_sync.health import sync_health


def main() -> int:
    db = SessionLocal()
    try:
        h = sync_health(db)
    finally:
        db.close()

    inb, out = h["inbound"], h["outbound"]
    print("=== Intégration CSA — statut ===")
    print(f"Santé globale : {'OK' if h['healthy'] else 'ATTENTION (voir erreurs)'}\n")
    print("Entrant (prescriptions CSA -> ordres) :")
    print(f"  dernier cycle   : {inb['last_run_at'] or '—'}")
    print(f"  watermark       : {inb['watermark'] or '—'}")
    print(f"  intégrées       : {inb['processed_count']}")
    print(f"  dernière erreur : {inb['last_error'] or 'aucune'}\n")
    print("Sortant (résultats validés -> CSA) :")
    print(f"  dernier cycle   : {out['last_run_at'] or '—'}")
    print(f"  remontés        : {out['pushed_count']}")
    print(f"  en attente      : {out['pending_ready']} prêt(s) / {out['pending_total']} item(s) prélevé(s)")
    print(f"  dernière erreur : {out['last_error'] or 'aucune'}\n")
    print(f"Ordres CSA : {h['orders']['csa_orders_total']} — items remontés : {h['orders']['items_pushed_total']}\n")

    unmapped = h["unmapped_exams"]
    if unmapped:
        print(f"Examens NON MAPPÉS à curer dans exam_map ({len(unmapped)} code(s)) :")
        for u in unmapped:
            print(f"  · {u['code']:16s} x{u['count']:<4d} {u['label'] or ''}")
    else:
        print("Aucun examen non mappe. [OK]")

    if "--json" in sys.argv:
        print("\n--- JSON ---")
        print(json.dumps(h, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
