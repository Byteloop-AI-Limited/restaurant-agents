"""Regression tests for process-wide library logging defaults."""

from types import SimpleNamespace

from restaurant_agent_runtime.config import logger_setting


def test_uvicorn_access_logs_are_enabled_unless_explicitly_disabled(monkeypatch):
    access_logger = SimpleNamespace(disabled=None)
    other_loggers = {
        "httpx": SimpleNamespace(setLevel=lambda _level: None),
        "httpcore": SimpleNamespace(setLevel=lambda _level: None),
    }

    original_get_logger = logger_setting.logging.getLogger

    def get_logger(name=None):
        if name == "uvicorn.access":
            return access_logger
        if name in other_loggers:
            return other_loggers[name]
        return original_get_logger(name)

    monkeypatch.setattr(logger_setting.logging, "getLogger", get_logger)
    monkeypatch.delenv("UVICORN_ACCESS_LOG", raising=False)
    logger_setting._configure_library_loggers()
    assert access_logger.disabled is False

    monkeypatch.setenv("UVICORN_ACCESS_LOG", "false")
    logger_setting._configure_library_loggers()
    assert access_logger.disabled is True
