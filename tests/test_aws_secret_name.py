"""
Tests that get_ordelo_agent_env resolves the secret name from configuration
    . Outside Lambda and with no explicit argument, it must use AWS_SETTINGS_SECRET_NAME
    . Loads utils/aws_setting.py in isolation with a fake boto3 client (no network)
"""

import json
from types import ModuleType, SimpleNamespace

from tests._stubs.loader import load_module


class _FakeSecretsClient:
    def __init__(self, payload):
        self._payload = payload
        self.requested_ids = []

    def get_secret_value(self, SecretId):
        self.requested_ids.append(SecretId)
        return {"SecretString": json.dumps(self._payload)}


def _build_boto3_stub(client):
    module = ModuleType("boto3")
    session = SimpleNamespace(client=lambda *a, **k: client)
    module.Session = lambda *a, **k: session
    module.client = lambda *a, **k: client
    return module


def test_secret_name_uses_env_var(monkeypatch):
    monkeypatch.setenv("AWS_SETTINGS_KEY_ID", "key")
    monkeypatch.setenv("AWS_SETTINGS_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SETTINGS_REGION", "eu-west-2")
    monkeypatch.setenv("AWS_SETTINGS_SECRET_NAME", "elai-agent-env")
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

    fake_client = _FakeSecretsClient({"sentinel": "value"})
    boto3_stub = _build_boto3_stub(fake_client)

    aws_setting = load_module(
        "aws_setting_under_test",
        "restaurant_agent_core.utils/aws_setting.py",
        monkeypatch,
        stubs={"boto3": boto3_stub},
    )

    # The module-level no-arg call at import time already resolved the name once.
    assert fake_client.requested_ids == ["elai-agent-env"]

    # An explicit no-arg call resolves it again from AWS_SETTINGS_SECRET_NAME.
    fake_client.requested_ids.clear()
    result = aws_setting.get_ordelo_agent_env()

    assert fake_client.requested_ids == ["elai-agent-env"]
    assert result == {"sentinel": "value"}
