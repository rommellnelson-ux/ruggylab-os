from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import EquipmentReagentRatio, Reagent, Result, StockMovement, User
from app.services.audit import log_audit_event


@dataclass(frozen=True)
class InsufficientStockItem:
    reagent_id: int
    reagent_name: str
    available: float
    required: float


class InsufficientStockError(Exception):
    def __init__(self, items: list[InsufficientStockItem]):
        self.items = items
        super().__init__("Insufficient reagent stock")


def consume_reagents_for_result(
    db: Session,
    *,
    result: Result,
    user: User | None,
    source: str,
) -> list[StockMovement]:
    if result.equipment_id is None:
        return []

    ratios = (
        db.query(EquipmentReagentRatio)
        .filter(
            EquipmentReagentRatio.equipment_id == result.equipment_id,
            EquipmentReagentRatio.is_active.is_(True),
        )
        .all()
    )
    if not ratios:
        return []

    locked_reagents = {
        reagent.id: reagent
        for reagent in (
            db.query(Reagent)
            .filter(Reagent.id.in_({ratio.reagent_id for ratio in ratios}))
            .with_for_update()
            .all()
        )
    }

    insufficient: list[InsufficientStockItem] = []
    consumptions: list[tuple[EquipmentReagentRatio, float]] = []
    for ratio in ratios:
        required = ratio.consumption_per_run * ratio.adjustment_factor
        if required <= 0:
            continue
        reagent = locked_reagents[ratio.reagent_id]
        if reagent.current_stock < required:
            insufficient.append(
                InsufficientStockItem(
                    reagent_id=reagent.id,
                    reagent_name=reagent.name,
                    available=reagent.current_stock,
                    required=required,
                )
            )
            continue
        consumptions.append((ratio, required))

    if insufficient:
        raise InsufficientStockError(insufficient)

    movements: list[StockMovement] = []
    for ratio, required in consumptions:
        reagent = locked_reagents[ratio.reagent_id]
        stock_before = reagent.current_stock
        stock_after = stock_before - required
        reagent.current_stock = stock_after
        movement = StockMovement(
            reagent_id=reagent.id,
            result_id=result.id,
            user_id=user.id if user else None,
            quantity_delta=-required,
            stock_before=stock_before,
            stock_after=stock_after,
            source=source,
        )
        db.add(movement)
        movements.append(movement)
        log_audit_event(
            db,
            user=user,
            event_type="stock.consume",
            entity_type="reagent",
            entity_id=str(reagent.id),
            payload={
                "result_id": result.id,
                "equipment_id": result.equipment_id,
                "reagent_name": reagent.name,
                "quantity_delta": -required,
                "stock_before": stock_before,
                "stock_after": stock_after,
                "source": source,
            },
        )
    return movements
