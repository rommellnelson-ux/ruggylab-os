"""Tests — Registre maître : preview, analyse rétrospective, import (B + C)."""

from __future__ import annotations

import uuid

from app.services.registre_analytics import compute_registre_analytics


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _tech(client) -> dict[str, str] | None:
    hdrs = _auth(client)
    u = uuid.uuid4().hex[:8]
    client.post(
        "/api/v1/users",
        headers=hdrs,
        json={"username": f"tech_{u}", "password": "TechPass123!", "role": "technician"},
    )
    tok = (
        client.post(
            "/api/v1/login/access-token", data={"username": f"tech_{u}", "password": "TechPass123!"}
        )
        .json()
        .get("access_token")
    )
    return {"Authorization": f"Bearer {tok}"} if tok else None


SAMPLE_ROWS = [
    {
        "nom": "M. ESSOH Paul",
        "date": "13/03/2025",
        "type_registre": "Hors CMU",
        "examens": "NFS ; Urée 0,13 ; Créat 77,2",
        "montant": 7000,
        "part_cmu": 0,
        "prescripteur": "Wognin",
        "provenance": "G.R",
    },
    {
        "nom": "KOUADJO Ahou Ruth",
        "date": "20/03/2025",
        "type_registre": "Hors CMU",
        "examens": "GE +145 trophozoïtes/champ",
        "montant": 2000,
        "part_cmu": 0,
        "prescripteur": "Wognin",
        "provenance": "G.R",
        "age": "32 ans",
    },
    {
        "nom": "KADJO Maxime",
        "date": "20/03/2025",
        "type_registre": "CMU",
        "examens": "CRP ; NFS ; GE négative",
        "montant": 7000,
        "part_cmu": 4900,
        "prescripteur": "Dr Wognin",
        "age": "46 ans",
    },
]


# ── C : Analyse rétrospective (unitaire) ────────────────────────────────────


class TestRegistreAnalyticsUnit:
    def test_totals_and_revenue(self):
        a = compute_registre_analytics(SAMPLE_ROWS)
        assert a["total_dossiers"] == 3
        assert a["revenue_total_fcfa"] == 16000
        assert a["cmu_part_fcfa"] == 4900
        assert a["by_type"] == {"Hors CMU": 2, "CMU": 1}

    def test_malaria_positivity(self):
        a = compute_registre_analytics(SAMPLE_ROWS)
        assert a["malaria_tested"] == 2  # 2 GE
        assert a["malaria_positive"] == 1  # une seule positive (+145)
        assert a["malaria_positivity_pct"] == 50.0

    def test_top_exams_and_months(self):
        a = compute_registre_analytics(SAMPLE_ROWS)
        exams = dict(a["top_exams"])
        assert exams.get("NFS") == 2
        assert exams.get("GE") == 2
        months = {m["month"]: m for m in a["by_month"]}
        assert "2025-03" in months
        assert months["2025-03"]["count"] == 3

    def test_handles_messy_dates(self):
        rows = [{"nom": "X", "date": "02-04-26", "examens": "NFS", "montant": 1000}]
        a = compute_registre_analytics(rows)
        assert any(m["month"] == "2026-04" for m in a["by_month"])


# ── C : endpoint analytics ──────────────────────────────────────────────────


class TestRegistreAnalyticsEndpoint:
    def test_analytics_endpoint(self, client):
        hdrs = _auth(client)
        r = client.post("/api/v1/registre/analytics", headers=hdrs, json={"rows": SAMPLE_ROWS})
        assert r.status_code == 200, r.text
        assert r.json()["total_dossiers"] == 3


# ── B : preview ─────────────────────────────────────────────────────────────


class TestRegistrePreview:
    def test_preview_recognition(self, client):
        hdrs = _auth(client)
        r = client.post("/api/v1/registre/preview", headers=hdrs, json={"rows": SAMPLE_ROWS})
        assert r.status_code == 200
        p = r.json()
        assert p["total_rows"] == 3
        # NFS,Urée,Créat,GE,CRP,NFS,GE = 7 examens, tous reconnus
        assert p["total_exams"] == 7
        assert p["recognized_exams"] == 7
        assert p["recognition_rate_pct"] == 100.0


# ── B : import (dry-run / garde-fou / écriture) ─────────────────────────────


class TestRegistreImport:
    def test_dry_run_counts_without_writing(self, client):
        hdrs = _auth(client)
        before = client.get("/api/v1/patients?limit=100", headers=hdrs).json()["meta"]["total"]
        r = client.post(
            "/api/v1/registre/import", headers=hdrs, json={"rows": SAMPLE_ROWS, "dry_run": True}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is True
        assert body["created_patients"] == 3
        assert body["created_results"] == 7
        after = client.get("/api/v1/patients?limit=100", headers=hdrs).json()["meta"]["total"]
        assert after == before  # rien écrit

    def test_real_import_requires_confirm(self, client):
        hdrs = _auth(client)
        r = client.post(
            "/api/v1/registre/import",
            headers=hdrs,
            json={"rows": SAMPLE_ROWS, "dry_run": False, "confirm": False},
        )
        assert r.status_code == 400

    def test_real_import_writes(self, client):
        hdrs = _auth(client)
        before = client.get("/api/v1/patients?limit=100", headers=hdrs).json()["meta"]["total"]
        r = client.post(
            "/api/v1/registre/import",
            headers=hdrs,
            json={"rows": SAMPLE_ROWS, "dry_run": False, "confirm": True},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is False
        assert body["created_patients"] == 3
        assert body["created_samples"] == 3
        assert body["created_results"] == 7
        after = client.get("/api/v1/patients?limit=100", headers=hdrs).json()["meta"]["total"]
        assert after == before + 3

    def test_import_estimates_birth_from_age(self, client):
        hdrs = _auth(client)
        r = client.post(
            "/api/v1/registre/import",
            headers=hdrs,
            json={"rows": SAMPLE_ROWS, "dry_run": False, "confirm": True},
        )
        # 1 ligne sans âge (ESSOH) → birth estimée par sentinelle
        assert r.json()["estimated_birth_dates"] >= 1

    def test_import_is_audited(self, client):
        hdrs = _auth(client)
        client.post(
            "/api/v1/registre/import",
            headers=hdrs,
            json={"rows": SAMPLE_ROWS, "dry_run": False, "confirm": True},
        )
        r = client.get("/api/v1/audit-events?event_type=registre.import", headers=hdrs)
        assert len(r.json()["items"]) >= 1

    def test_import_requires_officer(self, client):
        tech = _tech(client)
        if tech:
            r = client.post(
                "/api/v1/registre/import", headers=tech, json={"rows": SAMPLE_ROWS, "dry_run": True}
            )
            assert r.status_code == 403

    def test_row_missing_name_reported(self, client):
        hdrs = _auth(client)
        rows = [{"nom": "", "examens": "NFS"}, {"nom": "Bon Patient", "examens": "NFS"}]
        r = client.post(
            "/api/v1/registre/import",
            headers=hdrs,
            json={"rows": rows, "dry_run": False, "confirm": True},
        )
        body = r.json()
        assert body["created_patients"] == 1
        assert len(body["errors"]) == 1
        assert body["errors"][0]["row"] == 1
