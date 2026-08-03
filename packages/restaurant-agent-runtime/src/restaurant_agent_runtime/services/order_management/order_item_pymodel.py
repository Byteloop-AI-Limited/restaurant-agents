"""Canonical line-item model belonging to the FoodOrder aggregate."""

from pydantic import BaseModel


class OrderItem(BaseModel):
    """Persisted product line within a FoodOrder consistency boundary."""

    order_id: str
    sku: str
    quantity: int
    price: float
    product_name: str
    modifications: list[str] | None = None

