"""
Load shared application configuration from AWS Secrets Manager.
  . Uses AWS_SETTINGS_* credentials outside Lambda
  . Uses the Lambda execution role and AWS_REGION inside Lambda
  . Resolves explicit secret names before environment-specific defaults
  . Parses SecretString as JSON and fails fast when loading is unsuccessful
Functions/Classes
  . AwsSettings
    . secrets_client (property)
    . get_secret
  . is_running_on_lambda
  . get_secrets_client
  . get_agent_env
Module Values
  . agent_env
"""

# %%

# %%
import os
import boto3
from botocore.exceptions import ClientError
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class AwsSettings(BaseSettings):
    key_id: str
    access_key: str
    region: str
    secret_name: str

    model_config = SettingsConfigDict(
        env_prefix="AWS_SETTINGS_", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def secrets_client(self):
        """Get a boto3 secretsmanager client using the configured credentials."""
        session = boto3.Session(
            aws_access_key_id=self.key_id,
            aws_secret_access_key=self.access_key,
            region_name=self.region,
        )
        return session.client("secretsmanager")

    def get_secret(self):
        try:
            response = self.secrets_client.get_secret_value(SecretId=self.secret_name)
            return response["SecretString"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                print(f"Secret {self.secret_name} not found.")
            else:
                print(f"Error retrieving secret {self.secret_name}: {e}")
            return None


def is_running_on_lambda():
    """Detect if running inside AWS Lambda environment."""
    return "AWS_LAMBDA_FUNCTION_NAME" in os.environ


def get_secrets_client():
    """Return a boto3 secretsmanager client appropriate for the environment."""
    if is_running_on_lambda():
        # Use default session/credentials from Lambda execution role
        region = os.environ.get("AWS_REGION", "eu-west-2")
        session = boto3.Session(region_name=region)
        return session.client("secretsmanager")
    else:
        aws_settings = AwsSettings()
        return aws_settings.secrets_client


def get_agent_env(secret_name: str | None = None) -> dict:
    """Fetch and parse the application secret string."""
    client = get_secrets_client()
    # Use provided secret_name, or try to get from AwsSettings/environment
    if secret_name is not None:
        use_secret_name = secret_name
    elif not is_running_on_lambda():
        use_secret_name = AwsSettings().secret_name
    else:
        use_secret_name = os.environ.get("AGENT_SECRET_NAME", "agent-env")
    try:
        response = client.get_secret_value(SecretId=use_secret_name)
        return json.loads(response["SecretString"])
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise RuntimeError(
            f"Unable to read AWS secret '{use_secret_name}': {error_code}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"AWS secret '{use_secret_name}' does not contain valid JSON"
        ) from exc


# Secret name is resolved from AWS_SETTINGS_SECRET_NAME (via AwsSettings) so it
# is configurable per environment. Fail fast with a clear error if it is empty.
agent_env = get_agent_env(secret_name="restaurant-agents-env")
if not agent_env:
    raise RuntimeError(
        "Unable to load application settings from AWS Secrets Manager. "
        "Check AWS_SETTINGS_* configuration and IAM permissions."
    )

# Secret-management procedures belong in deployment documentation. Keeping them
# out of this module prevents shared runtime code from carrying environment- or
# restaurant-specific resource names.
