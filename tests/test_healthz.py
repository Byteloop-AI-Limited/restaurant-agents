"""Smoke test for the factory-owned ``/healthz`` liveness endpoint."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from restaurant_agent_runtime import (
    RestaurantIdentity,
    RestaurantPresentation,
    RestaurantSettingsBundle,
)
from restaurant_agent_runtime.web import AgentBindings, create_restaurant_app


class FakeDatabase:
    async def close_pool(self):
        return None


def test_healthz_returns_ok():
    identity = RestaurantIdentity("TEST", "test")
    settings = RestaurantSettingsBundle(
        project=SimpleNamespace(rest_ref=identity.rest_ref),
        database=FakeDatabase(),
        database_client=SimpleNamespace(),
        llm=SimpleNamespace(),
        payment=SimpleNamespace(),
        maps=SimpleNamespace(),
        waba=SimpleNamespace(),
    )
    app = create_restaurant_app(
        identity=identity,
        presentation=RestaurantPresentation(display_name="Test Restaurant"),
        graph_adapter_factory=lambda runtime: SimpleNamespace(runtime=runtime),
        agent_bindings=AgentBindings(
            callback_data_type=dict,
            select_service_sender=lambda **_: None,
        ),
        settings_loader=lambda _: settings,
        async_wa_factory=lambda _settings, _app: SimpleNamespace(),
        sync_wa_factory=lambda _settings: SimpleNamespace(),
        register_whatsapp_handlers=False,
        include_order_router=False,
        include_rider_router=False,
        include_thread_router=False,
    )

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
