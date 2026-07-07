"""Tests — Catalogue d'examens (réel) + parseur du registre maître."""

from __future__ import annotations

from app.services.exam_catalog import (
    EXAM_BY_CODE,
    EXAM_CATALOG,
    audit_exam_catalog,
    exam_catalog_entry,
    resolve_exam_code,
)
from app.services.registre_parser import (
    build_import_preview,
    parse_exam_cell,
    parse_exam_token,
    split_exams,
)


def _auth(client) -> dict[str, str]:
    token = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "change_me_admin_password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Catalogue ───────────────────────────────────────────────────────────────


class TestExamCatalog:
    def test_catalog_has_core_exams(self):
        codes = {e["code"] for e in EXAM_CATALOG}
        # Examens les plus fréquents du registre réel
        assert {"NFS", "GE", "CRP", "UREE", "GLYC", "ALAT", "ASAT", "CREAT"} <= codes

    def test_every_entry_well_formed(self):
        for e in EXAM_CATALOG:
            assert e["code"] and e["label"] and e["category"]
            assert isinstance(e["tat_minutes"], int) and e["tat_minutes"] > 0

    def test_resolve_canonical(self):
        assert resolve_exam_code("NFS") == "NFS"
        assert resolve_exam_code("nfs") == "NFS"

    def test_resolve_synonyms_and_accents(self):
        assert resolve_exam_code("Créat") == "CREAT"
        assert resolve_exam_code("Glycémie") == "GLYC"
        assert resolve_exam_code("Goutte épaisse") == "GE"
        assert resolve_exam_code("hémoglobine glyquée") == "HBA1C"

    def test_resolve_unknown(self):
        assert resolve_exam_code("ZZZ-inconnu") is None
        assert resolve_exam_code(None) is None

    def test_loinc_present_for_nfs(self):
        assert EXAM_BY_CODE["NFS"]["loinc"] == "58410-2"

    def test_catalog_exposes_preanalytic_and_technical_sheet(self):
        nfs = exam_catalog_entry("nfs")
        assert nfs is not None
        assert nfs["preanalytics"]["container"] == "Tube EDTA violet"
        assert nfs["preanalytics"]["bench"] == "Hematologie"
        assert nfs["technical_sheet"]["key_steps"]

    def test_default_workflow_metadata_for_less_detailed_exam(self):
        crp = exam_catalog_entry("CRP")
        assert crp is not None
        assert crp["preanalytics"]["bench"] == "Biochimie"
        assert crp["technical_sheet"]["qc_requirements"]
        assert crp["technical_sheet"]["validation_status"] == "needs_local_validation"
        assert crp["technical_sheet"]["local_document_ref"] is None

    def test_catalog_audit_does_not_claim_unapproved_sops_are_validated(self):
        audit = audit_exam_catalog()
        assert audit["total_exams"] == len(EXAM_CATALOG)
        assert audit["workflow_sheets_present"] == len(EXAM_CATALOG)
        assert audit["locally_validated"] == 0
        assert audit["pending_local_validation"] == len(EXAM_CATALOG)
        assert audit["issues"] == []


class TestCatalogEndpoint:
    def test_get_catalog(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/tat/catalog", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert any(e["code"] == "NFS" for e in data)
        nfs = next(e for e in data if e["code"] == "NFS")
        assert nfs["preanalytics"]["container"] == "Tube EDTA violet"

    def test_get_catalog_detail(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/tat/catalog/glycemie", headers=hdrs)
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == "GLYC"
        assert "fluorure" in data["preanalytics"]["container"].lower()

    def test_get_catalog_detail_unknown(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/tat/catalog/UNKNOWN", headers=hdrs)
        assert r.status_code == 404

    def test_catalog_audit_requires_officer_and_reports_pending_validation(self, client):
        hdrs = _auth(client)
        r = client.get("/api/v1/tat/catalog-audit", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["pending_local_validation"] == len(EXAM_CATALOG)

    def test_seed_uses_catalog(self, client):
        hdrs = _auth(client)
        r = client.post("/api/v1/tat/targets/seed-defaults", headers=hdrs)
        assert r.status_code == 200
        # Le catalogue compte plus de 5 examens → seed en crée davantage
        assert r.json()["created"] >= len(EXAM_CATALOG)
        codes = {t["exam_code"] for t in client.get("/api/v1/tat/targets", headers=hdrs).json()}
        assert {"NFS", "GE", "CRP", "ALAT", "ASAT"} <= codes


# ── Parseur ─────────────────────────────────────────────────────────────────


class TestParseExamToken:
    def test_simple_name(self):
        t = parse_exam_token("NFS")
        assert t["exam_code"] == "NFS"
        assert t["recognized"] is True
        assert t["numeric_value"] is None

    def test_name_with_french_decimal(self):
        t = parse_exam_token("Créat 77,2")
        assert t["exam_code"] == "CREAT"
        assert t["numeric_value"] == 77.2

    def test_uree_low_value(self):
        t = parse_exam_token("Urée 0,13")
        assert t["exam_code"] == "UREE"
        assert t["numeric_value"] == 0.13

    def test_ge_parasitemia_positive(self):
        t = parse_exam_token("GE +145 trophozoïtes/champ")
        assert t["exam_code"] == "GE"
        assert t["numeric_value"] == 145.0
        assert t["qualitative"] == "positive"

    def test_crp_negative(self):
        t = parse_exam_token("CRP négative")
        assert t["exam_code"] == "CRP"
        assert t["qualitative"] == "negative"

    def test_unrecognized_token(self):
        t = parse_exam_token("Examen bizarre 42")
        assert t["recognized"] is False
        assert t["exam_code"] is None
        assert t["numeric_value"] == 42.0

    def test_empty(self):
        t = parse_exam_token("")
        assert t["recognized"] is False
        assert t["raw"] == ""


class TestSplitAndCell:
    def test_split_multi(self):
        toks = split_exams("NFS ; Urée 0,13 ; Créat 77,2 ; Triglycérides")
        assert toks == ["NFS", "Urée 0,13", "Créat 77,2", "Triglycérides"]

    def test_parse_cell(self):
        parsed = parse_exam_cell("NFS ; Créat 77,2")
        assert len(parsed) == 2
        assert parsed[0]["exam_code"] == "NFS"
        assert parsed[1]["exam_code"] == "CREAT"

    def test_split_empty(self):
        assert split_exams(None) == []
        assert split_exams("") == []


class TestImportPreview:
    def test_preview_aggregates(self):
        rows = [
            {
                "nom": "M. ESSOH Paul",
                "date": "13/03/2025",
                "examens": "NFS ; Urée 0,13 ; Créat 77,2",
                "montant": 7000,
                "type_registre": "Hors CMU",
                "prescripteur": "Wognin",
            },
            {
                "nom": "KOUADJO Ahou",
                "date": "20/03/2025",
                "examens": "GE +145 trophozoïtes/champ",
                "montant": 2000,
                "type_registre": "Hors CMU",
            },
        ]
        prev = build_import_preview(rows)
        assert prev["total_rows"] == 2
        assert prev["total_exams"] == 4
        assert prev["recognized_exams"] == 4
        assert prev["recognition_rate_pct"] == 100.0
        assert prev["total_amount_fcfa"] == 9000

    def test_preview_flags_missing_name_and_unknown(self):
        rows = [{"nom": "", "examens": "ExamX 5 ; NFS"}]
        prev = build_import_preview(rows)
        assert prev["rows"][0]["warnings"] == ["nom patient manquant"]
        assert prev["unrecognized_exams"] == 1
        assert prev["recognized_exams"] == 1
        assert prev["top_unrecognized"]  # non vide
