"""Tests — rôle comptable (gestion) : accès finance, cloisonnement clinique.

Séparation des tâches : le comptable accède à la facturation/paiements et à
l'activité agrégée, mais à AUCUNE donnée clinique (patients, échantillons,
résultats…) même par appel direct de l'API.
"""

from __future__ import annotations

import uuid


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_accountant(client, admin) -> dict[str, str]:
    u = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": f"compta_{u}", "password": "ComptaPass123!", "role": "accountant"},
    )
    assert r.status_code in (200, 201), r.text
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"compta_{u}", "password": "ComptaPass123!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


class TestAccountantClinicalLockdown:
    def test_patients_denied(self, client):
        admin = _auth(client)
        compta = _make_accountant(client, admin)
        assert client.get("/api/v1/patients", headers=compta).status_code == 403

    def test_samples_denied(self, client):
        admin = _auth(client)
        compta = _make_accountant(client, admin)
        assert client.get("/api/v1/samples", headers=compta).status_code == 403

    def test_results_denied(self, client):
        admin = _auth(client)
        compta = _make_accountant(client, admin)
        assert client.get("/api/v1/results/cockpit", headers=compta).status_code == 403

    def test_imaging_denied(self, client):
        admin = _auth(client)
        compta = _make_accountant(client, admin)
        # le garde de routeur s'exécute avant la résolution du job → 403 (et non 404)
        r = client.get("/api/v1/imaging/malaria/jobs/inexistant", headers=compta)
        assert r.status_code == 403, r.text


class TestAccountantFinanceAccess:
    def test_stats_allowed(self, client):
        admin = _auth(client)
        compta = _make_accountant(client, admin)
        # activité agrégée : autorisée (valorisation), pas de données nominatives
        assert client.get("/api/v1/stats/summary?days=30", headers=compta).status_code == 200

    def test_billing_calculate_allowed(self, client):
        admin = _auth(client)
        compta = _make_accountant(client, admin)
        # le comptable peut accéder au moteur de facturation (pas un 403 de rôle)
        r = client.post(
            "/api/v1/billing/calculate",
            headers=compta,
            json={
                "patient_type": "non_assure",
                "cim10_code": "B54",
                "items": [{"dci": {"code": "ARTEMETHER-LUMEFANTRINE"}, "quantity": 1}],
            },
        )
        assert r.status_code != 403, r.text


class TestClinicalRolesUnaffected:
    def test_technician_still_reads_patients(self, client):
        admin = _auth(client)
        u = uuid.uuid4().hex[:8]
        client.post(
            "/api/v1/users",
            headers=admin,
            json={"username": f"tech_{u}", "password": "TechPass123!", "role": "technician"},
        )
        tok = client.post(
            "/api/v1/login/access-token",
            data={"username": f"tech_{u}", "password": "TechPass123!"},
        ).json()["access_token"]
        hdrs = {"Authorization": f"Bearer {tok}"}
        assert client.get("/api/v1/patients", headers=hdrs).status_code == 200
