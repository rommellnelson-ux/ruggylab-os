"""Tests — Référentiel biologique : seed, sélection, interprétation."""
from __future__ import annotations

from app.models import BiologicalReferenceRange
from app.services.bioref_data import BIOREF_SEED
from app.services.bioref_service import format_reference_range, interpret_value, normalize_sex


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ref(**over) -> BiologicalReferenceRange:
    base = dict(
        test_code="X", test_name="X", sex="ALL", age_min_years=0, age_max_years=120,
        lower_limit=None, upper_limit=None, unit="", normal_text=None,
        critical_low=None, critical_high=None,
    )
    base.update(over)
    return BiologicalReferenceRange(**base)


# ── Logique d'interprétation (unitaire, fidèle au spec fourni) ──────────────

class TestInterpretValue:
    def test_normal(self):
        assert interpret_value(15, _ref(lower_limit=13, upper_limit=17)) == "NORMAL"

    def test_bas(self):
        assert interpret_value(12.4, _ref(lower_limit=13, upper_limit=17)) == "BAS"

    def test_haut(self):
        assert interpret_value(18, _ref(lower_limit=13, upper_limit=17)) == "HAUT"

    def test_critique_bas_prioritaire(self):
        # 6 < critical_low 7 → CRITIQUE BAS (prioritaire sur BAS)
        assert interpret_value(6, _ref(lower_limit=13, upper_limit=17, critical_low=7)) == "CRITIQUE BAS"

    def test_critique_haut_prioritaire(self):
        assert interpret_value(25, _ref(lower_limit=13, upper_limit=17, critical_high=20)) == "CRITIQUE HAUT"

    def test_qualitatif_valeur_none(self):
        assert interpret_value(None, _ref(normal_text="Négatif")) == "Négatif"

    def test_borne_haute_seule(self):
        # AST : pas de borne basse, upper 40
        assert interpret_value(30, _ref(upper_limit=40, normal_text="< 40 UI/L")) == "NORMAL"
        assert interpret_value(50, _ref(upper_limit=40, normal_text="< 40 UI/L")) == "HAUT"

    def test_borne_basse_seule(self):
        # HDL homme : lower 0.40, pas d'upper
        assert interpret_value(0.5, _ref(lower_limit=0.40)) == "NORMAL"
        assert interpret_value(0.3, _ref(lower_limit=0.40)) == "BAS"


class TestFormatRange:
    def test_two_bounds(self):
        assert format_reference_range(_ref(lower_limit=13, upper_limit=17, unit="g/dL")) == "13 - 17 g/dL"

    def test_normal_text_priority(self):
        assert format_reference_range(_ref(upper_limit=40, unit="UI/L", normal_text="< 40 UI/L")) == "< 40 UI/L"

    def test_upper_only(self):
        assert format_reference_range(_ref(upper_limit=6, unit="mg/L")) == "< 6 mg/L"


class TestNormalizeSex:
    def test_mapping(self):
        assert normalize_sex("M") == "Homme"
        assert normalize_sex("F") == "Femme"
        assert normalize_sex("homme") == "Homme"
        assert normalize_sex(None) == "ALL"
        assert normalize_sex("xyz") == "ALL"


# ── Seed + endpoints ────────────────────────────────────────────────────────

class TestBiorefSeed:
    def test_seed_creates_all(self, client):
        hdrs = _auth(client)
        r = client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["created"] == len(BIOREF_SEED)
        # Idempotent
        assert client.post("/api/v1/bioref/seed-defaults", headers=hdrs).json()["created"] == 0

    def test_list_ranges_filtered(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
        r = client.get("/api/v1/bioref/ranges?test_code=HB", headers=hdrs)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2  # Homme + Femme
        assert {row["sex"] for row in rows} == {"Homme", "Femme"}

    def test_seed_requires_officer(self, client):
        hdrs = _auth(client)
        u = client.post("/api/v1/users", headers=hdrs,
                        json={"username": "tref", "password": "TechPass123!", "role": "technician"})
        assert u.status_code in (200, 201)
        tok = client.post("/api/v1/login/access-token",
                          data={"username": "tref", "password": "TechPass123!"}).json().get("access_token")
        if tok:
            r = client.post("/api/v1/bioref/seed-defaults", headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 403


# ── Interprétation bout-en-bout (reproduit l'exemple fourni) ────────────────

class TestInterpretEndpoint:
    def test_hb_homme_low_matches_example(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
        r = client.post("/api/v1/bioref/interpret", headers=hdrs,
                        json={"test_code": "HB", "value": 12.4, "sex": "M"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["result"] == 12.4
        assert d["unit"] == "g/dL"
        assert d["reference_range"] == "13 - 17 g/dL"
        assert d["flag"] == "BAS"
        assert "Anémie" in d["interpretation"]

    def test_hb_femme_uses_female_bounds(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
        # 12.4 est NORMAL pour une femme (12-16) mais BAS pour un homme (13-17)
        r = client.post("/api/v1/bioref/interpret", headers=hdrs,
                        json={"test_code": "HB", "value": 12.4, "sex": "F"})
        assert r.json()["flag"] == "NORMAL"

    def test_glycemie_critique(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
        r = client.post("/api/v1/bioref/interpret", headers=hdrs,
                        json={"test_code": "GLU_FAST", "value": 0.30})
        assert r.json()["flag"] == "CRITIQUE BAS"

    def test_potassium_critique_high(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
        r = client.post("/api/v1/bioref/interpret", headers=hdrs,
                        json={"test_code": "K", "value": 7.0})
        assert r.json()["flag"] == "CRITIQUE HAUT"

    def test_qualitative_malaria(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
        r = client.post("/api/v1/bioref/interpret", headers=hdrs,
                        json={"test_code": "MAL_GE", "value": None})
        d = r.json()
        assert d["flag"] == "Négatif"
        assert d["reference_range"] == "Négatif"

    def test_unknown_test(self, client):
        hdrs = _auth(client)
        client.post("/api/v1/bioref/seed-defaults", headers=hdrs)
        r = client.post("/api/v1/bioref/interpret", headers=hdrs,
                        json={"test_code": "ZZZ", "value": 1})
        assert "error" in r.json()
