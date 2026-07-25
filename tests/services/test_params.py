"""
Unit tests for generic parameter and filtering helpers
    . Covers dictionary filtering, projection, and callable/list/comparison filters
    . Covers SQL condition generation for strings, numbers, comparisons, and lists
    . Covers JSON validation, project-root lookup, and PYTHONPATH configuration
  Functions/Classes:
    . test_filter_dict_filters_and_selects_columns
    . test_filter_dict_supports_callables_and_comparisons
    . test_filter_dict_rejects_invalid_select_cols
    . test_get_sql_condition_builds_supported_conditions
    . test_get_sql_condition_rejects_invalid_types
    . test_is_json
    . test_get_project_root_success_and_failures
    . test_configure_pythonpath_uses_environment
"""

import subprocess

import pytest

from restaurant_agent_core.services import params


def test_filter_dict_filters_and_selects_columns():
    rows = [
        {"sku": "a", "price": 5, "qty": 1},
        {"sku": "b", "price": 9, "qty": 2},
    ]

    assert params.filter_dict(rows, sku="a") == [{"sku": "a", "price": 5, "qty": 1}]
    assert params.filter_dict(rows, sku=["a", "c"]) == [{"sku": "a", "price": 5, "qty": 1}]
    assert params.filter_dict(rows, select_cols=["sku"], price=9) == [{"sku": "b"}]
    assert params.filter_dict(rows, select_cols={"sku": "product_sku"}, price=9) == [{"product_sku": "b"}]


def test_filter_dict_supports_callables_and_comparisons():
    rows = [
        {"sku": "a", "price": 5, "qty": 1},
        {"sku": "b", "price": 9, "qty": 2},
        {"sku": "c", "price": None, "qty": 3},
    ]

    assert params.filter_dict(rows, sku=lambda value: value in {"a", "b"}) == rows[:2]
    assert params.filter_dict(rows, price__gte=6) == [rows[1]]
    assert params.filter_dict(rows, price__lte=5) == [rows[0]]


def test_filter_dict_rejects_invalid_select_cols():
    with pytest.raises(ValueError):
        params.filter_dict([{"a": 1}], select_cols="a")


def test_get_sql_condition_builds_supported_conditions():
    assert params.get_sql_condition(name="Elai") == "name = 'Elai'"
    assert params.get_sql_condition(name="Ela%") == "name LIKE 'Ela%'"
    assert params.get_sql_condition(price=9.95) == "price = 9.95"
    assert params.get_sql_condition(qty=2) == "qty = 2"
    assert params.get_sql_condition(price=">10") == "price > 10"
    assert params.get_sql_condition(price="<=20.5") == "price <= 20.5"
    assert params.get_sql_condition(status=["new", "paid"]) == "(status = 'new' OR status = 'paid')"
    assert params.get_sql_condition(qty=[1, ">3", "4%"] ) == "(qty = 1 OR qty > 3 OR qty LIKE '4%')"
    assert params.get_sql_condition(name="Elai", qty=1) == "name = 'Elai' AND qty = 1"


@pytest.mark.parametrize("kwargs", [{"bad": {"x": 1}}, {"bad": [object()]}])
def test_get_sql_condition_rejects_invalid_types(kwargs):
    with pytest.raises(TypeError):
        params.get_sql_condition(**kwargs)


@pytest.mark.parametrize("value,expected", [("{}", True), ("[]", True), ("1", True), ("not-json", False)])
def test_is_json(value, expected):
    assert params.is_json(value) is expected


def test_get_project_root_success_and_failures(monkeypatch):
    monkeypatch.setattr(params.subprocess, "check_output", lambda *args, **kwargs: b"/repo\n")
    assert params.get_project_root() == "/repo"

    def raise_called_process(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(params.subprocess, "check_output", raise_called_process)
    assert params.get_project_root() is None

    def raise_generic(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(params.subprocess, "check_output", raise_generic)
    assert params.get_project_root() is None


def test_configure_pythonpath_uses_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.setattr(params.sys, "path", [])
    params.configure_pythonpath()
    assert params.sys.path == [str(tmp_path)]

    monkeypatch.delenv("PYTHONPATH")
    monkeypatch.setattr(params.sys, "path", [])
    params.configure_pythonpath()
    assert params.sys.path
