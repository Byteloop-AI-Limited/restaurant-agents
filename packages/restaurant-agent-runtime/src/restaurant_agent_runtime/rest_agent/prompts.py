"""Application-owned prompt values consumed by the standard Agent runtime."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RestaurantPrompts:
    """Complete prompts for the standard triage, delivery, and takeaway agents."""

    triage: str
    delivery: str
    takeaway: str

    def __post_init__(self) -> None:
        for name in ("triage", "delivery", "takeaway"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} prompt must not be empty")
