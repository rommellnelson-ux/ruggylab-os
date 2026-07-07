import calendar
import datetime as dt
import hashlib
import json

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Dhis2Mapping, Result, Sample

INDICATORS = {
    "LAB_ACT_TOTAL": "Examens réalisés",
    "MAL_TEST_TOTAL": "Tests paludisme réalisés",
    "MAL_POS_TOTAL": "Tests paludisme positifs",
    "PRE_REJECT_TOTAL": "Prélèvements rejetés",
    "CRIT_NOTIFIED": "Valeurs critiques communiquées",
}

MALARIA_EXAMS = {"GE", "MALARIA", "PALU", "TDR_PALU"}
POSITIVE_TEXT = {"positif", "positive", "detected", "détecté", "present", "présent", "1"}


def month_bounds(period: str) -> tuple[dt.datetime, dt.datetime, dt.date]:
    try:
        year, month = int(period[:4]), int(period[4:])
        last_day = calendar.monthrange(year, month)[1]
    except (ValueError, IndexError) as exc:
        raise ValueError("La période doit respecter AAAAMM.") from exc
    start = dt.datetime(year, month, 1)
    end = dt.datetime(year, month, last_day, 23, 59, 59, 999999)
    return start, end, dt.date(year, month, last_day)


def _is_positive(data_points: dict) -> bool:
    for raw in data_points.values():
        value = raw.get("value") if isinstance(raw, dict) else raw
        if isinstance(value, bool) and value:
            return True
        if str(value).strip().lower() in POSITIVE_TEXT:
            return True
    return False


def calculate_indicators(db: Session, period: str) -> dict[str, int]:
    start, end, _ = month_bounds(period)
    results = (
        db.query(Result)
        .filter(
            Result.analysis_date >= start,
            Result.analysis_date <= end,
            Result.is_validated.is_(True),
        )
        .all()
    )
    malaria = [result for result in results if (result.exam_code or "").upper() in MALARIA_EXAMS]
    rejected = (
        db.query(Sample)
        .filter(
            Sample.collection_date >= start,
            Sample.collection_date <= end,
            Sample.status.in_(["rejected", "rejete", "rejeté"]),
        )
        .count()
    )
    return {
        "LAB_ACT_TOTAL": len(results),
        "MAL_TEST_TOTAL": len(malaria),
        "MAL_POS_TOTAL": sum(_is_positive(result.data_points) for result in malaria),
        "PRE_REJECT_TOTAL": rejected,
        "CRIT_NOTIFIED": sum(
            result.is_critical and result.critical_ack_at is not None for result in results
        ),
    }


def build_preview(
    db: Session,
    *,
    period: str,
    data_set_uid: str,
    org_unit_uid: str,
) -> dict:
    _, _, complete_date = month_bounds(period)
    values = calculate_indicators(db, period)
    mappings = (
        db.query(Dhis2Mapping)
        .filter(
            Dhis2Mapping.data_set_uid == data_set_uid,
            Dhis2Mapping.org_unit_uid == org_unit_uid,
            Dhis2Mapping.active.is_(True),
            or_(
                Dhis2Mapping.valid_from.is_(None),
                Dhis2Mapping.valid_from <= complete_date,
            ),
            or_(
                Dhis2Mapping.valid_to.is_(None),
                Dhis2Mapping.valid_to >= complete_date,
            ),
        )
        .all()
    )
    by_code = {mapping.internal_code: mapping for mapping in mappings}
    indicators = []
    warnings = []
    data_values = []
    for code, label in INDICATORS.items():
        mapping = by_code.get(code)
        if mapping is None:
            warnings.append(f"Mapping manquant pour {code}; indicateur non exporté.")
            continue
        item = {
            "code": code,
            "label": label,
            "value": values[code],
            "data_element_uid": mapping.data_element_uid,
            "category_option_combo_uid": mapping.category_option_combo_uid,
        }
        indicators.append(item)
        data_value = {"dataElement": mapping.data_element_uid, "value": str(values[code])}
        if mapping.category_option_combo_uid:
            data_value["categoryOptionCombo"] = mapping.category_option_combo_uid
        data_values.append(data_value)
    payload = {
        "dataSet": data_set_uid,
        "completeDate": complete_date.isoformat(),
        "period": period,
        "orgUnit": org_unit_uid,
        "dataValues": data_values,
    }
    return {
        "period": period,
        "data_set_uid": data_set_uid,
        "org_unit_uid": org_unit_uid,
        "complete_date": complete_date,
        "indicators": indicators,
        "warnings": warnings,
        "payload": payload,
    }


def payload_sha256(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
