"""Tests — Durcissement sécurité : SSRF, injection CSV, RBAC amend, audit, dry-run."""
from __future__ import annotations

import uuid

from app.utils.csv_safety import sanitize_csv_cell
from app.utils.url_safety import is_safe_external_url


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _tech_headers(client) -> dict[str, str] | None:
    hdrs = _auth(client)
    u = _uid()
    client.post(
        "/api/v1/users",
        headers=hdrs,
        json={"username": f"tech_{u}", "password": "TechPass123!", "role": "technician"},
    )
    tok = client.post(
        "/api/v1/login/access-token",
        data={"username": f"tech_{u}", "password": "TechPass123!"},
    ).json().get("access_token")
    return {"Authorization": f"Bearer {tok}"} if tok else None


# ── Garde anti-SSRF (unitaire) ──────────────────────────────────────────────

class TestUrlSafety:
    def test_blocks_loopback(self):
        assert is_safe_external_url("http://127.0.0.1/hook") is False
        assert is_safe_external_url("http://localhost/hook") is False

    def test_blocks_private_ranges(self):
        assert is_safe_external_url("http://10.0.0.5/x") is False
        assert is_safe_external_url("http://192.168.1.1/x") is False
        assert is_safe_external_url("http://172.16.0.1/x") is False

    def test_blocks_cloud_metadata(self):
        assert is_safe_external_url("http://169.254.169.254/latest/meta-data") is False

    def test_blocks_non_http_scheme(self):
        assert is_safe_external_url("file:///etc/passwd") is False
        assert is_safe_external_url("ftp://example.com/x") is False
        assert is_safe_external_url("gopher://1.2.3.4/x") is False

    def test_blocks_empty(self):
        assert is_safe_external_url(None) is False
        assert is_safe_external_url("") is False

    def test_allows_public_ip(self):
        assert is_safe_external_url("https://8.8.8.8/hook") is True


# ── Neutralisation injection CSV (unitaire) ─────────────────────────────────

class TestCsvSafety:
    def test_prefixes_formula_chars(self):
        assert sanitize_csv_cell("=1+1") == "'=1+1"
        assert sanitize_csv_cell("+SUM(A1)") == "'+SUM(A1)"
        assert sanitize_csv_cell("-2") == "'-2"
        assert sanitize_csv_cell("@cmd") == "'@cmd"

    def test_leaves_safe_strings(self):
        assert sanitize_csv_cell("hello") == "hello"
        assert sanitize_csv_cell("result.amend") == "result.amend"

    def test_passes_non_strings(self):
        assert sanitize_csv_cell(42) == 42
        assert sanitize_csv_cell(None) is None
        assert sanitize_csv_cell(3.14) == 3.14


# ── Injection CSV bout-en-bout via l'export d'audit ─────────────────────────

class TestAuditCsvInjection:
    def test_malicious_entity_id_is_neutralized(self, client):
        hdrs = _auth(client)
        # Crée un patient dont l'IPP commence par '=' → entity_id potentiellement dangereux
        # On force via un audit indirect : création réactif avec nom piégé.
        client.post(
            "/api/v1/reagents",
            headers=hdrs,
            json={"name": f"=HYPERLINK-{_uid()}", "unit": "u", "current_stock": 1, "alert_threshold": 0},
        )
        r = client.get("/api/v1/audit-events/export.csv", headers=hdrs)
        assert r.status_code == 200
        # Aucune cellule ne doit commencer par '=' brut (préfixée par apostrophe)
        for line in r.text.splitlines()[1:]:
            for cell in line.split(","):
                stripped = cell.strip().strip('"')
                assert not stripped.startswith("="), f"Cellule non neutralisée: {cell}"


# ── RBAC : amend réservé officier + révocation signature ────────────────────

class TestAmendRbac:
    def _make_result(self, client, hdrs) -> int:
        pid = client.post(
            "/api/v1/patients",
            headers=hdrs,
            json={"ipp_unique_id": f"SH-{_uid()}", "first_name": "A", "last_name": "B",
                  "birth_date": "1980-01-01", "sex": "M"},
        ).json()["id"]
        sid = client.post(
            "/api/v1/samples",
            headers=hdrs,
            json={"barcode": f"SH-{_uid()}", "patient_id": pid, "status": "Recu"},
        ).json()["id"]
        return client.post(
            "/api/v1/results",
            headers=hdrs,
            json={"sample_id": sid, "data_points": {"WBC": 5.0}, "is_critical": False},
        ).json()["id"]

    def test_technician_cannot_amend(self, client):
        admin = _auth(client)
        rid = self._make_result(client, admin)
        tech = _tech_headers(client)
        if tech:
            r = client.patch(
                f"/api/v1/results/{rid}/amend",
                headers=tech,
                json={"data_points": {"WBC": 6.0}, "amendment_reason": "Tentative technicien"},
            )
            assert r.status_code == 403

    def test_amend_revokes_signature(self, client):
        hdrs = _auth(client)
        rid = self._make_result(client, hdrs)
        # Signe le compte-rendu
        sign = client.post(
            f"/api/v1/reports/results/{rid}/sign",
            headers=hdrs,
            json={"signature_meaning": "Validation biologiste"},
        )
        assert sign.status_code == 201, sign.text
        # Amende → la signature doit être révoquée
        amend = client.patch(
            f"/api/v1/results/{rid}/amend",
            headers=hdrs,
            json={"data_points": {"WBC": 7.0}, "amendment_reason": "Correction après signature"},
        )
        assert amend.status_code == 200, amend.text
        sig = client.get(f"/api/v1/reports/results/{rid}/signature", headers=hdrs).json()
        assert sig["revoked_at"] is not None


# ── Audit des changements d'auto-validation ─────────────────────────────────

class TestAutoValidationAudit:
    def test_config_creation_is_audited(self, client):
        hdrs = _auth(client)
        client.post(
            "/api/v1/auto-validation/config",
            headers=hdrs,
            json={"name": f"Audit-{_uid()}", "require_not_critical": True,
                  "require_no_delta": False, "require_all_flags_normal": False},
        )
        r = client.get(
            "/api/v1/audit-events?event_type=auto_validation.config.create", headers=hdrs
        )
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1

    def test_run_is_audited(self, client):
        hdrs = _auth(client)
        client.post(
            "/api/v1/auto-validation/config",
            headers=hdrs,
            json={"name": f"Run-{_uid()}", "require_not_critical": False,
                  "require_no_delta": False, "require_all_flags_normal": False},
        )
        client.post("/api/v1/auto-validation/run", headers=hdrs)
        r = client.get("/api/v1/audit-events?event_type=auto_validation.run", headers=hdrs)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1


# ── Traçabilité accès dossier patient ───────────────────────────────────────

class TestPatientAccessAudit:
    def test_history_view_is_audited(self, client):
        hdrs = _auth(client)
        pid = client.post(
            "/api/v1/patients",
            headers=hdrs,
            json={"ipp_unique_id": f"PA-{_uid()}", "first_name": "A", "last_name": "B",
                  "birth_date": "1980-01-01", "sex": "F"},
        ).json()["id"]
        client.get(f"/api/v1/patients/{pid}/history", headers=hdrs)
        r = client.get(
            f"/api/v1/audit-events?event_type=patient.history.view&entity_type=patient", headers=hdrs
        )
        assert r.status_code == 200
        assert any(e["entity_id"] == str(pid) for e in r.json()["items"])


# ── Import en lot : dry-run + savepoint + borne ─────────────────────────────

class TestBulkImportHardening:
    def test_dry_run_does_not_persist(self, client):
        hdrs = _auth(client)
        u = _uid()
        csv = (
            "ipp_unique_id,first_name,last_name,birth_date,sex\n"
            f"DRY-{u},Test,Dry,1990-01-01,M\n"
        )
        r = client.post(
            "/api/v1/bulk-import/patients", headers=hdrs, json={"csv": csv, "dry_run": True}
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["dry_run"] is True
        assert data["created"] == 1
        # Le patient ne doit PAS exister réellement
        search = client.get(f"/api/v1/patients?q=DRY-{u}", headers=hdrs).json()
        assert all(p["ipp_unique_id"] != f"DRY-{u}" for p in search["items"])

    def test_valid_row_survives_bad_row(self, client):
        """Une ligne invalide (savepoint annulé) n'empêche pas la ligne valide."""
        hdrs = _auth(client)
        u = _uid()
        csv = (
            "ipp_unique_id,first_name,last_name,birth_date,sex\n"
            f"GOOD-{u},Valid,One,1990-01-01,M\n"
            f"BAD-{u},Bad,Two,not-a-date,F\n"
        )
        r = client.post("/api/v1/bulk-import/patients", headers=hdrs, json={"csv": csv})
        data = r.json()
        assert data["created"] == 1
        assert len(data["errors"]) == 1
        # La bonne ligne est bien persistée
        search = client.get(f"/api/v1/patients?q=GOOD-{u}", headers=hdrs).json()
        assert any(p["ipp_unique_id"] == f"GOOD-{u}" for p in search["items"])

    def test_too_many_rows_rejected(self, client):
        hdrs = _auth(client)
        header = "ipp_unique_id,first_name,last_name,birth_date,sex\n"
        rows = "".join(f"R{i},F,L,1990-01-01,M\n" for i in range(5001))
        r = client.post("/api/v1/bulk-import/patients", headers=hdrs, json={"csv": header + rows})
        assert r.status_code == 413
