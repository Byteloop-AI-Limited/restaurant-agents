"""Request-scoped access to explicitly assembled application dependencies."""

from fastapi import Request

from restaurant_agent_core.runtime import GraphAdapter, RestaurantRuntime


def get_restaurant_runtime(request: Request) -> RestaurantRuntime:
    return request.app.state.restaurant_runtime


def get_graph_adapter(request: Request) -> GraphAdapter:
    return request.app.state.graph_adapter
