"""Application-owned prompt values consumed by the standard Agent runtime."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RestaurantPrompts:
    """Complete prompts for the standard agents.

    `dinein` is optional: supplying it activates the optional standard
    dine-in node (see `agents/dine_in.py`). Its default of `None` keeps every
    app that does not configure dine-in unaffected, including equality
    comparisons against a `RestaurantPrompts` built with only the three
    required prompts.
    """

    triage: str
    delivery: str
    takeaway: str
    dinein: str | None = None

    def __post_init__(self) -> None:
        for name in ("triage", "delivery", "takeaway"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} prompt must not be empty")
        if self.dinein is not None and not self.dinein.strip():
            raise ValueError("dinein prompt must not be empty when supplied")
