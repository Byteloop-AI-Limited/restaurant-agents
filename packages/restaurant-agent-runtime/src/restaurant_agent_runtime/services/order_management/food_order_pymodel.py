"""Canonical persisted FoodOrder aggregate model."""

from pydantic import BaseModel


class FoodOrder(BaseModel):
    """Validated FoodOrder data used at persistence and integration boundaries."""

    order_id: str
    order_number: str
    seq_id: int | None = None
    recipient: str
    notes: str | None = None
    thread_id: str
    action: str
    total_price: float
    final_order_value: float | None = None
    rest_cost: float | None = None
    service_charge: float | None = None
    delivery_fee: float | None = None
    small_order_fee: float | None = None
    commission_rate: float | None = None
    payment_status: str
