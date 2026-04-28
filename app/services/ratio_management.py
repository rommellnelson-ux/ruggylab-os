from sqlalchemy.orm import Session

from app.models import EquipmentReagentRatio, EquipmentReagentRatioVersion, User


def create_ratio_version(
    db: Session,
    *,
    ratio: EquipmentReagentRatio,
    changed_by_user: User | None,
    change_reason: str | None = None,
) -> EquipmentReagentRatioVersion:
    latest_version = (
        db.query(EquipmentReagentRatioVersion)
        .filter(EquipmentReagentRatioVersion.ratio_id == ratio.id)
        .order_by(EquipmentReagentRatioVersion.version_number.desc())
        .first()
    )
    version_number = 1 if latest_version is None else latest_version.version_number + 1
    version = EquipmentReagentRatioVersion(
        ratio_id=ratio.id,
        version_number=version_number,
        equipment_id=ratio.equipment_id,
        reagent_id=ratio.reagent_id,
        consumption_per_run=ratio.consumption_per_run,
        adjustment_factor=ratio.adjustment_factor,
        notes=ratio.notes,
        is_active=ratio.is_active,
        changed_by_user_id=changed_by_user.id if changed_by_user else None,
        change_reason=change_reason,
    )
    db.add(version)
    return version
