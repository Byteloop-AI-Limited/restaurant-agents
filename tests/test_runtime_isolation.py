from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from restaurant_agent_runtime import (
    RestaurantIdentity,
    RestaurantPresentation,
    RestaurantSettingsBundle,
)
from restaurant_agent_runtime.config.waba_setting import WabaBusinessSettings
from restaurant_agent_runtime.web import AgentBindings, create_restaurant_app


class FakeDatabase:
    def __init__(self):
        self.closed = False

    async def close_pool(self):
        self.closed = True


class FakeWaClient:
    def __init__(self, namespace: str):
        self.namespace = namespace
        self.handlers = []
        self.sent = []

    def add_handlers(self, *handlers):
        self.handlers.extend(handlers)

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(id=f"{self.namespace}-message")

    async def get_business_phone_number(self, *, phone_id):
        assert phone_id == f"{self.namespace}-phone"
        return SimpleNamespace(
            display_phone_number=f"+44-{self.namespace}",
            webhook_configuration={
                "application": f"https://{self.namespace}-app.example.test/",
                "whatsapp_business_account": (
                    f"https://{self.namespace}-waba.example.test/"
                ),
            },
        )


class FakeGraphAdapter:
    def __init__(self, runtime):
        self.runtime = runtime
        self.calls = []

    async def run_rest_graph_with_custom_msg(self, recipient: str, **kwargs):
        self.calls.append((recipient, kwargs))
        return "ok"

    async def debug_state(self, recipient: str, full_state: bool = False):
        return {"recipient": recipient, "full_state": full_state}

    async def debug_state_values(self, recipient=None, config=None):
        return {"recipient": recipient, "config": config}

    async def debug_state_by_thread(self, thread_id: str, full_state: bool = False):
        return {"thread_id": thread_id, "full_state": full_state}


def _settings(identity: RestaurantIdentity) -> RestaurantSettingsBundle:
    return RestaurantSettingsBundle(
        project=SimpleNamespace(rest_ref=identity.rest_ref),
        database=FakeDatabase(),
        database_client=SimpleNamespace(),
        llm=SimpleNamespace(model="fake"),
        payment=SimpleNamespace(),
        maps=SimpleNamespace(),
        waba=SimpleNamespace(
            namespace=identity.waba_namespace,
            waa_account_id=f"{identity.waba_namespace}-account",
            waa_phone_id=f"{identity.waba_namespace}-phone",
            waa_app_id=f"{identity.waba_namespace}-app",
            waa_token=f"{identity.waba_namespace}-token-secret",
            waa_app_secret=f"{identity.waba_namespace}-app-secret",
            waa_callback_url=(
                f"https://{identity.waba_namespace}-configured.example.test/"
            ),
        ),
    )


def _build_test_app(identity: RestaurantIdentity, *, register_whatsapp_handlers: bool = False):
    created = {}

    def async_factory(waba, app):
        client = FakeWaClient(waba.namespace)
        created["async_client"] = client
        return client

    def sync_factory(waba):
        client = SimpleNamespace(namespace=waba.namespace)
        created["sync_client"] = client
        return client

    def graph_factory(runtime):
        adapter = FakeGraphAdapter(runtime)
        created["adapter"] = adapter
        return adapter

    app = create_restaurant_app(
        identity=identity,
        presentation=RestaurantPresentation(display_name=identity.rest_ref),
        graph_adapter_factory=graph_factory,
        agent_bindings=AgentBindings(
            callback_data_type=dict,
            select_service_sender=lambda **_: None,
        ),
        settings_loader=_settings,
        async_wa_factory=async_factory,
        sync_wa_factory=sync_factory,
        register_whatsapp_handlers=register_whatsapp_handlers,
        include_order_router=False,
        include_rider_router=False,
        include_thread_router=True,
    )
    return app, created


def test_two_apps_keep_exact_clients_and_identities_isolated():
    sfcs_app, sfcs = _build_test_app(RestaurantIdentity("SFCS", "sfcs"))
    bnat_app, bnat = _build_test_app(RestaurantIdentity("BNAT", "bnat"))

    assert sfcs["adapter"].runtime.async_wa_client is sfcs["async_client"]
    assert bnat["adapter"].runtime.async_wa_client is bnat["async_client"]
    assert sfcs["async_client"] is not bnat["async_client"]
    assert (
        sfcs["adapter"].runtime.operational_lookups
        is not bnat["adapter"].runtime.operational_lookups
    )

    with TestClient(sfcs_app) as sfcs_client, TestClient(bnat_app) as bnat_client:
        assert sfcs_client.get("/identity").json() == {
            "rest_ref": "SFCS",
            "waba_namespace": "sfcs",
        }
        assert bnat_client.get("/identity").json() == {
            "rest_ref": "BNAT",
            "waba_namespace": "bnat",
        }


def test_select_enquiry_registers_both_a_button_and_a_selection_handler():
    """/SelectEnquiry now arrives as either a CallbackButton (menus already
    delivered before this release) or a CallbackSelection (new SectionList
    rows, ADR-0023). Both handler types must be registered and both must
    actually match a real update — asserting the handler object exists is
    not enough, since CallbackButtonHandler silently never fires for a
    CallbackSelection update."""
    from pywa.handlers import CallbackButtonHandler, CallbackSelectionHandler

    app, created = _build_test_app(
        RestaurantIdentity("BNAT", "bnat"), register_whatsapp_handlers=True
    )
    handlers = created["async_client"].handlers

    button_handlers = [h for h in handlers if isinstance(h, CallbackButtonHandler)]
    selection_handlers = [h for h in handlers if isinstance(h, CallbackSelectionHandler)]

    button_update = SimpleNamespace(
        data='{"action":"/SelectEnquiry","rest_ref":"bnat"}', _txt_fields=("data",)
    )
    selection_update = SimpleNamespace(
        data='{"action":"/SelectEnquiry","rest_ref":"bnat"}', _txt_fields=("data",)
    )

    assert any(h.check(None, button_update) for h in button_handlers)
    assert any(h.check(None, selection_update) for h in selection_handlers)


@pytest.mark.parametrize(
    ("rest_ref", "namespace"),
    [("BNAT", "bnat"), ("SFCS", "sfcs")],
)
def test_details_exposes_selected_runtime_identity_without_raw_secrets(
    rest_ref, namespace, monkeypatch
):
    monkeypatch.setattr(
        "restaurant_agent_runtime.waba_callback._restaurant_master_details",
        lambda runtime: {
            "admins": [f"{runtime.identity.rest_ref}-admin"],
            "service_hours": {"monday": [["10:00", "22:00"]]},
        },
    )
    monkeypatch.setattr(
        "restaurant_agent_runtime.waba_callback.application_url_details",
        lambda _: (
            {
                "ORDELO_APP_URL": "https://ordelo.example.test",
                "BNAT_APP_URL": "https://bnat.example.test",
                "SFCS_APP_URL": "https://sfcs.example.test",
                "ELAS_APP_URL": "https://elas.example.test",
            },
            {},
        ),
    )
    app, _ = _build_test_app(RestaurantIdentity(rest_ref, namespace))

    with TestClient(app) as client:
        response = client.get("/details")

    assert response.status_code == 200
    assert response.json() == {
        "rest_ref": rest_ref,
        "waba_namespace": namespace,
        "waba_id": f"{namespace}-account",
        "phone_id": f"{namespace}-phone",
        "app_id": f"{namespace}-app",
        "token_hint": "****cret",
        "app_secret_hint": "****cret",
        "validate_updates": False,
        "display_number": f"+44-{namespace}",
        "admins": [f"{rest_ref}-admin"],
        "service_hours": {"monday": [["10:00", "22:00"]]},
        "callback_url": f"https://{namespace}-waba.example.test/",
        "configured_callback_url": (f"https://{namespace}-configured.example.test/"),
        "ordelo_services": {
            "ORDELO_APP_URL": "https://ordelo.example.test",
            "BNAT_APP_URL": "https://bnat.example.test",
            "SFCS_APP_URL": "https://sfcs.example.test",
            "ELAS_APP_URL": "https://elas.example.test",
        },
        "details_errors": {},
    }
    assert f"{namespace}-token-secret" not in response.text
    assert f"{namespace}-app-secret" not in response.text


def test_cache_reset_is_runtime_local_and_validates_scope():
    app, created = _build_test_app(RestaurantIdentity("SFCS", "sfcs"))
    cache = created["adapter"].runtime.operational_lookups
    cache._app_urls["ORDELO"] = object()

    with TestClient(app) as client:
        response = client.post(
            "/internal/cache/reset?scope=operational_config&app_ref=ORDELO"
        )
        invalid_scope = client.post(
            "/internal/cache/reset?scope=overwatch&app_ref=ORDELO"
        )
        unknown_app = client.post(
            "/internal/cache/reset?scope=operational_config&app_ref=OTHER"
        )

    assert response.status_code == 200
    assert response.json()["removed_entries"]["operational_config"] == 1
    assert invalid_scope.status_code == 422
    assert unknown_app.status_code == 404


def test_cross_restaurant_thread_route_is_404_without_graph_side_effects():
    app, created = _build_test_app(RestaurantIdentity("BNAT", "bnat"))
    payload = {
        "job_run_id": str(uuid4()),
        "threads": [{"thread_id": "SFCS-thread-1", "recipient": "447"}],
    }

    with TestClient(app) as client:
        response = client.post(
            "/thread-hooks/SFCS/terminate-stale-active-threads", json=payload
        )

    assert response.status_code == 404
    assert created["adapter"].calls == []


def test_stale_thread_contract_keeps_202_prefix_check_and_bound_graph():
    app, created = _build_test_app(RestaurantIdentity("BNAT", "bnat"))
    job_run_id = uuid4()
    payload = {
        "job_run_id": str(job_run_id),
        "threads": [{"thread_id": "BNAT-thread-1", "recipient": "447"}],
    }

    with TestClient(app) as client:
        response = client.post(
            "/thread-hooks/BNAT/terminate-stale-active-threads", json=payload
        )

    assert response.status_code == 202
    assert response.json() == {
        "job_run_id": str(job_run_id),
        "received_count": 1,
        "queued_count": 1,
    }
    assert created["adapter"].calls[0][0] == "447"
    assert created["adapter"].runtime.async_wa_client is created["async_client"]


def test_stale_thread_prefix_mismatch_is_rejected_before_graph_call():
    app, created = _build_test_app(RestaurantIdentity("BNAT", "bnat"))
    payload = {
        "job_run_id": str(uuid4()),
        "threads": [{"thread_id": "SFCS-thread-1", "recipient": "447"}],
    }

    with TestClient(app) as client:
        response = client.post(
            "/thread-hooks/BNAT/terminate-stale-active-threads", json=payload
        )

    assert response.status_code == 400
    assert created["adapter"].calls == []


def _waba_values(namespace: str) -> dict[str, object]:
    prefix = f"{namespace}_"
    return {
        f"{prefix}waa_account_id": "account",
        f"{prefix}waa_business_account_id": "business",
        f"{prefix}waa_token": "token",
        f"{prefix}waa_phone_id": 123,
        f"{prefix}waa_callback_url": "https://example.test/webhook",
        f"{prefix}waa_verify_token": "verify",
        f"{prefix}waa_app_id": "app",
        f"{prefix}waa_app_secret": "secret",
        f"{prefix}waa_private_key_password": "password",
    }


def test_waba_namespace_has_no_fallback():
    values = _waba_values("sfcs")
    assert WabaBusinessSettings.for_namespace("sfcs", values).waa_token == "token"
    with pytest.raises(ValidationError):
        WabaBusinessSettings.for_namespace("bnat", values)


def test_async_waba_client_disables_signature_validation(monkeypatch):
    """Signature validation is intentionally off for every app; see ADR-0022."""
    captured = {}

    class FakeWhatsApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "restaurant_agent_runtime.config.waba_setting.WhatsApp", FakeWhatsApp
    )
    settings = WabaBusinessSettings.for_namespace("bnat", _waba_values("bnat"))
    server = object()
    settings.create_async_client(server=server)

    assert captured["server"] is server
    assert captured["validate_updates"] is False
    assert captured["app_secret"] == "secret"
    assert captured["phone_id"] == 123


def test_sync_waba_client_uses_waba_account_id(monkeypatch):
    captured = {}

    class FakeWhatsAppSync:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "restaurant_agent_runtime.config.waba_setting.WhatsAppSync", FakeWhatsAppSync
    )
    settings = WabaBusinessSettings.for_namespace("bnat", _waba_values("bnat"))
    settings.create_sync_client()

    assert captured["business_account_id"] == "account"


def test_app_packages_do_not_import_each_other_or_global_wa_clients():
    repo_root = Path(__file__).resolve().parents[1]
    app_sources = {
        "sfcs": "\n".join(
            path.read_text()
            for path in (repo_root / "apps/sfcs/src/sfcs_agent").rglob("*.py")
        ),
        "bnat": "\n".join(
            path.read_text()
            for path in (repo_root / "apps/bnat/src/bnat_agent").rglob("*.py")
        ),
        "elas": "\n".join(
            path.read_text()
            for path in (repo_root / "apps/elas/src/elas_agent").rglob("*.py")
        ),
    }
    core_source = "\n".join(
        path.read_text()
        for path in (
            repo_root / "packages/restaurant-agent-runtime/src/restaurant_agent_runtime"
        ).rglob("*.py")
    )

    package_names = {"sfcs": "sfcs_agent", "bnat": "bnat_agent", "elas": "elas_agent"}
    for app, source in app_sources.items():
        for other_app, package_name in package_names.items():
            if other_app == app:
                continue
            assert f"from {package_name}" not in source
    for forbidden in ("_async_wa_client", "_sync_wa_client", "waba_business_settings"):
        assert forbidden not in core_source
