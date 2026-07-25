"""Compatibility exports for the application-factory architecture.

There is intentionally no shared ``app`` object: SFCS and BNAT assemble isolated
applications in their own ``main`` modules.
"""

from restaurant_agent_core.web import AgentBindings, create_restaurant_app

__all__ = ["AgentBindings", "create_restaurant_app"]
