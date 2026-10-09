"""
Payment receipt carries the customer's private order-page link
    . Calls payment_complete directly with stub runtimes (matches test_specialist_lifecycle_updates.py)
    . The link is best effort: any failure sends the receipt unchanged
    . fetch_order_page_link never calls out without a key and never logs the link
  Functions/Classes:
    . _runtime
    . _order
    . test_receipt_has_order_tracking_button
    . test_receipt_has_no_button_when_no_link
    . test_replayed_delivery_event_fetches_nothing
    . test_fetch_*
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import BackgroundTasks

from restaurant_agent_runtime.services import order_link
from restaurant_agent_runtime.watomation.routers import order_event_hooks

URL = "https://restaurant.ordelo.app/o/" + "a" * 43
KEY = "k" * 40


def _order(action):
    return SimpleNamespace(
        recipient="447000000010",
        thread_id="ELAS-thread-10",
        action=action,
        order_id="ORD-10",
        order_number="ELAS-ABCD-10",
        payment_status="requires_capture",
    )


def _runtime():
    wa_client = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(id="wamid.receipt"))
    )
    return SimpleNamespace(
        identity=SimpleNamespace(matches=lambda value: value == "ELAS"),
        settings=SimpleNamespace(
            database_client=object(), ordelo=SimpleNamespace(web_key=KEY)
        ),
        async_wa_client=wa_client,
        operational_lookups=SimpleNamespace(
            get_app_url=lambda ref: "https://ordelo.example"
        ),
    )


def _patch(monkeypatch, link, state=None):
    monkeypatch.setattr(
        order_event_hooks,
        "build_wa_order_reciept_for_cust",
        lambda **_: ("Order Header", "Receipt Body"),
    )
    fetch = AsyncMock(return_value=link)
    monkeypatch.setattr(order_event_hooks, "fetch_order_page_link", fetch)
    adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value=state or {}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    return fetch, adapter


async def _pay(action, adapter):
    runtime, order = _runtime(), _order(action)
    tasks = BackgroundTasks()
    await order_event_hooks.payment_complete(
        rest_ref="ELAS",
        recipient=order.recipient,
        thread_id=order.thread_id,
        food_order=order,
        background_tasks=tasks,
        runtime=runtime,
        graph_adapter=adapter,
    )
    for task in tasks.tasks:  # release the takeaway lifecycle gate we reserved
        lock = task.kwargs.get("lock")
        if lock is not None and lock.locked():
            lock.release()
    return runtime.async_wa_client.send_message


@pytest.mark.parametrize("action", ["delivery", "takeaway"])
async def test_receipt_has_order_tracking_button(monkeypatch, action):
    fetch, adapter = _patch(monkeypatch, URL)
    send = await _pay(action, adapter)
    fetch.assert_awaited_once()
    assert fetch.await_args.args[1:] == ("ELAS-ABCD-10", "447000000010")
    kwargs = send.await_args.kwargs
    assert kwargs["buttons"].title == "Order Tracking"
    assert kwargs["buttons"].url == URL
    assert "Receipt Body" in kwargs["text"]
    assert URL not in kwargs["text"]  # the link lives only in the button


@pytest.mark.parametrize("action", ["delivery", "takeaway"])
async def test_receipt_has_no_button_when_no_link(monkeypatch, action):
    _, adapter = _patch(monkeypatch, None)
    send = await _pay(action, adapter)
    send.assert_awaited_once()
    assert "buttons" not in send.await_args.kwargs
    assert "Track your order" not in send.await_args.kwargs["text"]


async def test_replayed_delivery_event_fetches_nothing(monkeypatch):
    fetch, adapter = _patch(monkeypatch, URL)
    monkeypatch.setattr(
        order_event_hooks, "_is_duplicate_delivery_payment_event", lambda *_: True
    )
    send = await _pay("delivery", adapter)
    fetch.assert_not_awaited()
    send.assert_not_awaited()


# --- fetch_order_page_link -------------------------------------------------------


def _client(monkeypatch, handler):
    """Route the service's httpx client through a mock transport; record its kwargs."""
    seen = {}
    real = httpx.AsyncClient

    def make(**kwargs):
        seen.update(kwargs)
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(order_link.httpx, "AsyncClient", make)
    return seen


@pytest.mark.parametrize("key", ["", "short", None])
async def test_fetch_makes_no_call_without_a_usable_key(monkeypatch, key):
    def boom(request):
        raise AssertionError("no HTTP call expected")

    _client(monkeypatch, boom)
    runtime = _runtime()
    runtime.settings.ordelo.web_key = key
    assert await order_link.fetch_order_page_link(runtime, "ELAS-ABCD-10", "44700") is None


async def test_fetch_returns_url_and_sends_key_with_2s_timeout(monkeypatch):
    captured = {}

    def handler(request):
        captured["request"] = request
        return httpx.Response(201, json={"url": URL, "expires_at": "x"})

    seen = _client(monkeypatch, handler)
    got = await order_link.fetch_order_page_link(_runtime(), "ELAS-ABCD-10", "447000000010")
    assert got == URL
    assert seen["timeout"] == 2.0 and seen["follow_redirects"] is False
    request = captured["request"]
    assert str(request.url) == "https://ordelo.example/web/access/whatsapp-link"
    assert request.headers["X-Ordelo-Web-Key"] == KEY


@pytest.mark.parametrize("status", [401, 403, 404, 409, 503])
async def test_fetch_non_201_returns_none(monkeypatch, status):
    _client(monkeypatch, lambda r: httpx.Response(status, json={"error": "x"}))
    assert await order_link.fetch_order_page_link(_runtime(), "ELAS-ABCD-10", "44700") is None


@pytest.mark.parametrize("body", [{"url": "http://insecure/o/x"}, {"url": 5}, {}])
async def test_fetch_rejects_non_https_or_missing_url(monkeypatch, body):
    _client(monkeypatch, lambda r: httpx.Response(201, json=body))
    assert await order_link.fetch_order_page_link(_runtime(), "ELAS-ABCD-10", "44700") is None


async def test_fetch_timeout_returns_none_and_logs_no_link(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    _client(monkeypatch, timeout)
    logged = []
    monkeypatch.setattr(
        order_link.logger, "warning", lambda msg, *args: logged.append(msg.format(*args))
    )
    assert await order_link.fetch_order_page_link(_runtime(), "ELAS-ABCD-10", "44700") is None
    assert logged and all("/o/" not in line and KEY not in line for line in logged)


async def test_fetch_makes_no_call_when_bundle_has_no_ordelo_settings(monkeypatch):
    def boom(request):
        raise AssertionError("no HTTP call expected")

    _client(monkeypatch, boom)
    runtime = _runtime()
    runtime.settings.ordelo = None
    assert await order_link.fetch_order_page_link(runtime, "ELAS-ABCD-10", "44700") is None
