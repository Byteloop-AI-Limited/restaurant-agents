"""
Async database pool stubs for unit tests
    . Mimics the async context-manager shape used by psycopg pools and cursors
    . Records executed SQL statements and parameters for assertions
    . Supports configurable fetchone and fetchall responses
  Functions/Classes:
    . FakeCursor
    . FakeConnection
    . FakeAsyncPool
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeCursor:
    fetchone_result: Any = None
    fetchall_result: list[Any] = field(default_factory=list)
    executed: list[tuple[str, Any]] = field(default_factory=list)
    executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = field(default_factory=list)
    rowcount: int = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None):
        self.executed.append((query, params))

    async def executemany(self, query, params_seq):
        self.executemany_calls.append((query, list(params_seq)))

    async def fetchone(self):
        return self.fetchone_result

    async def fetchall(self):
        return self.fetchall_result


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def cursor(self, *args, **kwargs):
        return self._cursor


class FakeAsyncPool:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self.cursor_obj = FakeCursor(
            fetchone_result=fetchone_result,
            fetchall_result=fetchall_result or [],
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def connection(self):
        return FakeConnection(self.cursor_obj)
