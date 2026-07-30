"""Standard Restaurant Agent runtime and its small public composition surface."""

from typing import Any

from .prompts import RestaurantPrompts

__all__ = ["RestaurantGraphAdapter", "RestaurantPrompts"]


def __getattr__(name: str) -> Any:
    if name == "RestaurantGraphAdapter":
        from .agent_runner import RestaurantGraphAdapter

        return RestaurantGraphAdapter
    raise AttributeError(name)
