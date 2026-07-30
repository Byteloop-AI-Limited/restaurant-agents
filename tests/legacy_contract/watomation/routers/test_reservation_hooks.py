"""
Unit tests for reservation webhook router functions
    . Loads reservation_hooks with stubbed config, Supabase, and WhatsApp client
    . Tests router functions directly without a FastAPI server
    . Covers submission, confirmation, decline, validation errors, not found, and internal error branches
  Functions/Classes:
    . FakeRequest
    . reservation_module
    . test_reservation_form_submitted_success_and_validation_errors
    . test_reservation_confirmed_and_declined_send_messages
    . test_reservation_not_found_and_internal_errors
"""

import pytest
from fastapi import HTTPException

from tests._stubs.config_stub import FakeSupabaseClient, build_config_stub
from tests._stubs.loader import load_module


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


@pytest.fixture
def reservation_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.client_ordelo = FakeSupabaseClient(
        table_data={"reservation": [{"recipient": "447000000001"}]}
    )
    module = load_module(
        "test_reservation_hooks_module",
        "restaurant_agent_runtime.watomation/routers/reservation_hooks.py",
        monkeypatch,
        {"config": config_stub},
    )
    module._config_stub = config_stub
    return module


@pytest.mark.asyncio
async def test_reservation_form_submitted_success_and_validation_errors(reservation_module):
    result = await reservation_module.reservation_form_submitted(
        "elas",
        FakeRequest({"reservation_id": "ELAS-RESV-22"}),
    )

    assert result == {
        "status": "success",
        "rest_ref": "ELAS",
        "reservation_id": "ELAS-RESV-22",
        "recipient": "447000000001",
    }
    assert "reservation request has been received" in reservation_module._async_wa_client.sent_messages[-1]["text"]

    with pytest.raises(HTTPException) as missing:
        await reservation_module.reservation_form_submitted("elas", FakeRequest({}))
    assert missing.value.status_code == 400

    with pytest.raises(HTTPException) as bad_format:
        await reservation_module.reservation_form_submitted(
            "elas", FakeRequest({"reservation_id": "BADFORMAT"})
        )
    assert bad_format.value.status_code == 400

    with pytest.raises(HTTPException) as mismatch:
        await reservation_module.reservation_form_submitted(
            "chks", FakeRequest({"reservation_id": "ELAS-RESV-22"})
        )
    assert mismatch.value.status_code == 400


@pytest.mark.asyncio
async def test_reservation_confirmed_and_declined_send_messages(reservation_module):
    confirmed = await reservation_module.reservation_confirmed("elas", "ELAS-RESV-22")
    assert confirmed == {
        "status": "success",
        "rest_ref": "ELAS",
        "reservation_id": "ELAS-RESV-22",
        "recipient": "447000000001",
    }
    assert "Great news" in reservation_module._async_wa_client.sent_messages[-1]["text"]

    declined = await reservation_module.reservation_declined("elas", "ELAS-RESV-22")
    assert declined == {
        "status": "success",
        "rest_ref": "ELAS",
        "reservation_id": "ELAS-RESV-22",
        "recipient": "447000000001",
    }
    assert "unable to confirm" in reservation_module._async_wa_client.sent_messages[-1]["text"]


@pytest.mark.asyncio
async def test_reservation_not_found_and_internal_errors(reservation_module):
    reservation_module.client_ordelo = FakeSupabaseClient(table_data={"reservation": []})

    with pytest.raises(HTTPException) as not_found:
        await reservation_module.reservation_confirmed("elas", "ELAS-RESV-22")
    assert not_found.value.status_code == 404

    class BrokenClient:
        def table(self, table_name):
            raise RuntimeError("db down")

    reservation_module.client_ordelo = BrokenClient()
    with pytest.raises(HTTPException) as internal:
        await reservation_module.reservation_declined("elas", "ELAS-RESV-22")
    assert internal.value.status_code == 500
