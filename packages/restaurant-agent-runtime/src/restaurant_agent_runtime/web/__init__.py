"""FastAPI assembly for restaurant applications."""

from .app_factory import AgentBindings, create_restaurant_app

__all__ = ["AgentBindings", "create_restaurant_app"]
