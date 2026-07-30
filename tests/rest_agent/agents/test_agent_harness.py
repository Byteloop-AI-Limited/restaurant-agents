"""
Unit tests for rest_agent.agents.agent_harness pure helpers
    . Verifies _normalize_min_order_value coerces strings, currency-prefixed values,
      None, empty string, and falls back to 0.0 on garbage
    . Verifies _transfer_check_delivery_retain blocks transfer when retain_thread is set
    . Verifies _run_transfer_guards aggregates guard results

SFCS is single-restaurant, so there is no rest_ref guard (unlike elai).
"""

from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
    _normalize_min_order_value,
    _run_transfer_guards,
    _transfer_check_delivery_retain,
)


def test_normalize_min_order_value_handles_numeric_strings():
    assert _normalize_min_order_value("12.5") == 12.5
    assert _normalize_min_order_value(8) == 8.0


def test_normalize_min_order_value_handles_currency_prefix():
    assert _normalize_min_order_value("£12.5") == 12.5
    assert _normalize_min_order_value("$ 9.99") == 9.99


def test_normalize_min_order_value_returns_zero_on_none_or_blank():
    assert _normalize_min_order_value(None) == 0.0
    assert _normalize_min_order_value("") == 0.0


def test_normalize_min_order_value_returns_zero_on_garbage():
    assert _normalize_min_order_value("abc!@#") == 0.0


def test_transfer_check_delivery_retain_returns_block_when_retained():
    cmd = _transfer_check_delivery_retain({"retain_thread": True}, tool_call_id="tc-1")

    assert cmd is not None
    assert cmd.update["messages"][0].tool_call_id == "tc-1"


def test_transfer_check_delivery_retain_returns_none_when_not_retained():
    assert (
        _transfer_check_delivery_retain({"retain_thread": False}, tool_call_id="tc-1")
        is None
    )


def test_run_transfer_guards_blocks_when_delivery_retained():
    cmd = _run_transfer_guards({"retain_thread": True}, "tc-1")
    assert cmd is not None


def test_run_transfer_guards_returns_none_when_all_clear():
    assert _run_transfer_guards({"retain_thread": False}, "tc-1") is None
