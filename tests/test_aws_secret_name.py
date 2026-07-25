"""
Tests for shared AWS Secrets Manager configuration loading.
    . Covers explicit, local, and Lambda secret-name resolution
    . Covers AWS client and malformed JSON failures
    . Loads utils/aws_setting.py in isolation with a fake boto3 client (no network)
"""

import json
from types import ModuleType, SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from tests._stubs.loader import load_module


class _FakeSecretsClient:
    def __init__(self, payload):
        self.secret_string = json.dumps(payload)
        self.error = None
        self.requested_ids = []

    def get_secret_value(self, SecretId):
        self.requested_ids.append(SecretId)
        if self.error is not None:
            raise self.error
        return {"SecretString": self.secret_string}


def _build_boto3_stub(client):
    module = ModuleType("boto3")
    module.session_calls = []

    def create_session(*args, **kwargs):
        module.session_calls.append((args, kwargs))
        return SimpleNamespace(client=lambda *a, **k: client)

    module.Session = create_session
    return module


def _set_local_aws_settings(monkeypatch, secret_name="agent-env"):
    monkeypatch.setenv("AWS_SETTINGS_KEY_ID", "key")
    monkeypatch.setenv("AWS_SETTINGS_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SETTINGS_REGION", "eu-west-2")
    monkeypatch.setenv("AWS_SETTINGS_SECRET_NAME", secret_name)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)


def test_secret_name_uses_env_var(monkeypatch):
    _set_local_aws_settings(monkeypatch)
    fake_client = _FakeSecretsClient({"sentinel": "value"})
    boto3_stub = _build_boto3_stub(fake_client)

    aws_setting = load_module(
        "aws_setting_under_test",
        "restaurant_agent_core.utils/aws_setting.py",
        monkeypatch,
        stubs={"boto3": boto3_stub},
    )

    assert fake_client.requested_ids == ["agent-env"]

    fake_client.requested_ids.clear()
    result = aws_setting.get_agent_env()

    assert fake_client.requested_ids == ["agent-env"]
    assert result == {"sentinel": "value"}


def test_explicit_secret_name_is_used_exactly(monkeypatch):
    _set_local_aws_settings(monkeypatch)
    fake_client = _FakeSecretsClient({"sentinel": "value"})
    aws_setting = load_module(
        "aws_setting_explicit_name_under_test",
        "restaurant_agent_core.utils/aws_setting.py",
        monkeypatch,
        stubs={"boto3": _build_boto3_stub(fake_client)},
    )
    fake_client.requested_ids.clear()

    aws_setting.get_agent_env("explicit-agent-env")
    aws_setting.get_agent_env("")

    assert fake_client.requested_ids == ["explicit-agent-env", ""]


@pytest.mark.parametrize(
    ("configured_name", "expected_name"),
    [("lambda-agent-env", "lambda-agent-env"), (None, "agent-env")],
)
def test_lambda_uses_execution_role_and_generic_fallback(
    monkeypatch, configured_name, expected_name
):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "restaurant-agent")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    if configured_name is None:
        monkeypatch.delenv("AGENT_SECRET_NAME", raising=False)
    else:
        monkeypatch.setenv("AGENT_SECRET_NAME", configured_name)
    fake_client = _FakeSecretsClient({"sentinel": "value"})
    boto3_stub = _build_boto3_stub(fake_client)

    load_module(
        f"aws_setting_lambda_{expected_name}_under_test",
        "restaurant_agent_core.utils/aws_setting.py",
        monkeypatch,
        stubs={"boto3": boto3_stub},
    )

    assert fake_client.requested_ids == [expected_name]
    assert boto3_stub.session_calls == [((), {"region_name": "eu-west-1"})]


def test_client_error_is_raised_as_runtime_error(monkeypatch):
    _set_local_aws_settings(monkeypatch)
    fake_client = _FakeSecretsClient({"sentinel": "value"})
    aws_setting = load_module(
        "aws_setting_client_error_under_test",
        "restaurant_agent_core.utils/aws_setting.py",
        monkeypatch,
        stubs={"boto3": _build_boto3_stub(fake_client)},
    )
    fake_client.error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "GetSecretValue",
    )

    with pytest.raises(
        RuntimeError,
        match="Unable to read AWS secret 'explicit-agent-env': AccessDeniedException",
    ):
        aws_setting.get_agent_env("explicit-agent-env")


def test_malformed_json_is_raised_as_runtime_error(monkeypatch):
    _set_local_aws_settings(monkeypatch)
    fake_client = _FakeSecretsClient({"sentinel": "value"})
    aws_setting = load_module(
        "aws_setting_malformed_json_under_test",
        "restaurant_agent_core.utils/aws_setting.py",
        monkeypatch,
        stubs={"boto3": _build_boto3_stub(fake_client)},
    )
    fake_client.secret_string = "{invalid-json"

    with pytest.raises(
        RuntimeError,
        match="AWS secret 'explicit-agent-env' does not contain valid JSON",
    ):
        aws_setting.get_agent_env("explicit-agent-env")
