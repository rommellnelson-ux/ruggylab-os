"""Smoke test bout-en-bout d'une instance RuggyLab OS déjà démarrée.

Valide le flux « labo réel » complet sur une instance UAT/préprod :
santé → connexion → patient → échantillon → prescription d'examens → fil →
résultat → facturation → encaissement → synthèse comptable.

Usage (instance lancée sur http://127.0.0.1:8000) :

    python -m scripts.uat_smoke
    # ou en ciblant une autre URL / d'autres identifiants :
    UAT_BASE_URL=https://uat.exemple.ci \
    UAT_ADMIN_USER=admin UAT_ADMIN_PASSWORD='...' python -m scripts.uat_smoke

Sort en code 0 si tout passe, 1 sinon. N'écrit jamais en production : à lancer
uniquement contre une instance de test dédiée.
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx

# Console Windows (cp1252) : éviter UnicodeEncodeError sur les accents et « → ».
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = os.environ.get("UAT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api/v1"
ADMIN_USER = os.environ.get("UAT_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get(
    "UAT_ADMIN_PASSWORD", os.environ.get("FIRST_SUPERUSER_PASSWORD", "SuperAdmin2026!SecurePass")
)

_suffix = uuid.uuid4().hex[:8]
_passed = 0
_failed = 0


def _ok(label: str) -> None:
    global _passed
    _passed += 1
    print(f"  [OK]   {label}")


def _fail(label: str, detail: str) -> None:
    global _failed
    _failed += 1
    print(f"  [FAIL] {label} -> {detail}")


def _check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        _ok(label)
    else:
        _fail(label, detail or "condition non remplie")
    return condition


def main() -> int:
    print(f"Smoke test RuggyLab OS sur {BASE_URL}\n")
    client = httpx.Client(timeout=15.0)

    # 1. Santé
    try:
        r = client.get(f"{API}/health")
        if not _check("santé /health", r.status_code == 200, f"HTTP {r.status_code}"):
            return 1
    except httpx.HTTPError as exc:
        _fail("santé /health", f"instance injoignable ({exc})")
        return 1

    # 2. Connexion administrateur
    r = client.post(
        f"{API}/login/access-token",
        data={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
    )
    if not _check("connexion admin", r.status_code == 200, r.text[:160]):
        return 1
    admin = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # 3. Patient
    r = client.post(
        f"{API}/patients",
        headers=admin,
        json={
            "ipp_unique_id": f"SMOKE-{_suffix}",
            "first_name": "Smoke",
            "last_name": "Test",
            "birth_date": "1990-01-01",
            "sex": "M",
        },
    )
    if not _check("création patient", r.status_code in (200, 201), r.text[:160]):
        return 1
    patient_id = r.json()["id"]

    # 4. Échantillon (code-barres)
    barcode = f"SMK-{_suffix}"
    r = client.post(
        f"{API}/samples",
        headers=admin,
        json={"barcode": barcode, "patient_id": patient_id, "status": "Recu"},
    )
    if not _check("création échantillon", r.status_code in (200, 201), r.text[:160]):
        return 1
    sample_id = r.json()["id"]

    # 4b. Résolution par code-barres (saisie labo réel)
    r = client.get(f"{API}/samples/by-barcode/{barcode}", headers=admin)
    _check(
        "résolution code-barres", r.status_code == 200 and r.json()["id"] == sample_id, r.text[:120]
    )

    # 5. Prescription d'examens
    r = client.post(
        f"{API}/exam-orders",
        headers=admin,
        json={
            "patient_id": patient_id,
            "prescriber": "Dr Smoke",
            "priority": "urgent",
            "exams": [{"exam_code": "NFS"}, {"exam_code": "GE"}],
        },
    )
    if not _check("création prescription", r.status_code in (200, 201), r.text[:160]):
        return 1
    order_id = r.json()["id"]

    # 6. Rattachement de l'échantillon (le fil)
    r = client.post(
        f"{API}/exam-orders/{order_id}/collect", headers=admin, json={"barcode": barcode}
    )
    _check("rattachement échantillon", r.status_code == 200, r.text[:160])

    # 7. Résultat NFS
    r = client.post(
        f"{API}/results",
        headers=admin,
        json={"sample_id": sample_id, "exam_code": "NFS", "data_points": {"WBC": 5.0}},
    )
    _check("création résultat", r.status_code in (200, 201), r.text[:160])

    # 8. Suivi du fil : au moins un examen résulté
    r = client.get(f"{API}/exam-orders/{order_id}/thread", headers=admin)
    thread_ok = r.status_code == 200 and r.json().get("resulted_exams", 0) >= 1
    _check("suivi du fil (résultat rattaché)", thread_ok, r.text[:160])

    # 9. Comptable + facturation
    compta_user = f"smoke_compta_{_suffix}"
    client.post(
        f"{API}/users",
        headers=admin,
        json={"username": compta_user, "password": "SmokeCompta123!", "role": "accountant"},
    )
    r = client.post(
        f"{API}/login/access-token",
        data={"username": compta_user, "password": "SmokeCompta123!"},
    )
    if not _check("connexion comptable", r.status_code == 200, r.text[:160]):
        return _summary()
    compta = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # Cloisonnement : le comptable ne voit pas le clinique
    r = client.get(f"{API}/patients", headers=compta)
    _check("cloisonnement comptable (patients 403)", r.status_code == 403, f"HTTP {r.status_code}")

    # Facture (non assuré : reste à charge intégral)
    r = client.post(
        f"{API}/invoices",
        headers=compta,
        json={
            "patient_label": "Smoke Test",
            "patient_type": "UNINSURED",
            "lines": [
                {
                    "exam_code": "NFS",
                    "label": "Numération",
                    "quantity": 1,
                    "unit_price_xof": "5000",
                },
                {
                    "exam_code": "GE",
                    "label": "Goutte épaisse",
                    "quantity": 1,
                    "unit_price_xof": "2500",
                },
            ],
        },
    )
    if not _check("émission facture", r.status_code in (200, 201), r.text[:160]):
        return _summary()
    invoice = r.json()
    _check(
        "total facture = 7500 FCFA",
        float(invoice["patient_due_xof"]) == 7500,
        str(invoice.get("patient_due_xof")),
    )
    invoice_id = invoice["id"]

    # Encaissement partiel puis solde
    client.post(
        f"{API}/invoices/{invoice_id}/payments", headers=compta, json={"amount_xof": "5000"}
    )
    r = client.post(
        f"{API}/invoices/{invoice_id}/payments", headers=compta, json={"amount_xof": "2500"}
    )
    _check(
        "encaissement → payée", r.status_code == 200 and r.json()["status"] == "paid", r.text[:160]
    )

    # Synthèse comptable
    r = client.get(f"{API}/invoices/summary", headers=compta)
    _check(
        "synthèse comptable", r.status_code == 200 and r.json()["invoice_count"] >= 1, r.text[:160]
    )

    return _summary()


def _summary() -> int:
    print(f"\nRésultat : {_passed} OK, {_failed} échec(s).")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
