"""
Unit tests for utils_common.reservation_management.reservation_db_ops
    . Loads the module with stubbed config (project_settings.salt, logger)
    . Verifies ReservationModel generates 4-character encoded reservation IDs
    . Verifies _create_reservation_id rejects non-4-digit recipients
    . Exercises ReservationHandler against FakeAsyncPool
    . Verifies process_reservation_into_db and update_reservation_in_db happy paths
  Functions/Classes:
    . reservation_module
    . test_reservation_model_generates_id_with_rest_ref_prefix
    . test_reservation_model_rejects_non_digit_recipient
    . test_reservation_handler_get_seq_num
    . test_reservation_handler_create_record_executes_insert
    . test_reservation_handler_update_record_returns_true_when_rows_affected
    . test_reservation_handler_update_record_returns_false_when_no_rows
    . test_process_reservation_into_db_returns_reservation_id
    . test_update_reservation_in_db_returns_handler_result
"""

import pytest

from tests._stubs.loader import load_module
from tests._stubs.pool_stub import FakeAsyncPool


@pytest.fixture
def reservation_module(monkeypatch):
    return load_module(
        "test_reservation_module",
        "restaurant_agent_runtime.services/reservation_management/reservation_db_ops.py",
        monkeypatch,
    )


def test_reservation_model_generates_id_with_rest_ref_prefix(reservation_module):
    record = reservation_module.ReservationModel(
        rest_ref="bnat", seq_id=1, recipient="447000001234", thread_id="t-1"
    )

    assert record.reservation_id.startswith("BNAT-")
    assert record.reservation_id.endswith("-1")
    middle = record.reservation_id.split("-")[1]
    assert len(middle) == 4
    assert middle.isalpha()


def test_reservation_model_rejects_non_digit_recipient(reservation_module):
    with pytest.raises(ValueError):
        reservation_module.ReservationModel(
            rest_ref="BNAT", seq_id=1, recipient="447aaa", thread_id="t-1"
        )


@pytest.mark.asyncio
async def test_reservation_handler_get_seq_num(reservation_module):
    pool = FakeAsyncPool(fetchone_result={"get_next_daily_seq": 42})
    handler = reservation_module.ReservationHandler(pool)

    seq = await handler.get_seq_num()

    assert seq == 42
    assert "get_next_daily_seq" in pool.cursor_obj.executed[0][0]


@pytest.mark.asyncio
async def test_reservation_handler_create_record_executes_insert(reservation_module):
    pool = FakeAsyncPool()
    handler = reservation_module.ReservationHandler(pool)
    record = reservation_module.ReservationModel(
        rest_ref="BNAT", seq_id=1, recipient="447000001234", thread_id="t-1"
    )

    ok = await handler.create_reservation_record(record)

    assert ok is True
    sql, _ = pool.cursor_obj.executed[0]
    assert "INSERT INTO" in sql


@pytest.mark.asyncio
async def test_reservation_handler_update_record_returns_true_when_rows_affected(
    reservation_module,
):
    pool = FakeAsyncPool()
    pool.cursor_obj.rowcount = 1
    handler = reservation_module.ReservationHandler(pool)

    ok = await handler.update_reservation_record("ELAS-ABCD-1")

    assert ok is True


@pytest.mark.asyncio
async def test_reservation_handler_update_record_returns_false_when_no_rows(
    reservation_module,
):
    pool = FakeAsyncPool()
    pool.cursor_obj.rowcount = 0
    handler = reservation_module.ReservationHandler(pool)

    ok = await handler.update_reservation_record("ELAS-ABCD-1")

    assert ok is False


@pytest.mark.asyncio
async def test_process_reservation_into_db_returns_reservation_id(reservation_module):
    pool = FakeAsyncPool(fetchone_result={"get_next_daily_seq": 7})

    result = await reservation_module.process_reservation_into_db(
        pool, "447000001234", "t-1", rest_ref="SFCS"
    )

    assert isinstance(result, str)
    assert result.startswith("SFCS-")


@pytest.mark.asyncio
async def test_update_reservation_in_db_returns_handler_result(reservation_module):
    pool = FakeAsyncPool()
    pool.cursor_obj.rowcount = 1

    result = await reservation_module.update_reservation_in_db(pool, "ELAS-ABCD-1")

    assert result is True
