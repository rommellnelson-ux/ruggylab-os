from pydantic import BaseModel


class ValidateOrderRequest(BaseModel):
    reagent_id: int | None = None
    order_reference: str | None = None
    notes: str | None = None
