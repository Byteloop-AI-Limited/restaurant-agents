#!/bin/sh
set -eu

APP_NAME="${FLY_APP_NAME:-bnat-agent}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE="${FLY_ENV_FILE:-$SCRIPT_DIR/.env}"
AWS_SECRET_NAME="${FLY_AWS_SECRET_NAME:-}"

if ! command -v fly >/dev/null 2>&1; then
    echo "Error: flyctl is not installed or is not on PATH." >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: environment file not found: $ENV_FILE" >&2
    exit 1
fi

if [ -z "$AWS_SECRET_NAME" ]; then
    echo "Error: FLY_AWS_SECRET_NAME must name the AWS secret for this app." >&2
    exit 1
fi

for key in AWS_SETTINGS_KEY_ID AWS_SETTINGS_ACCESS_KEY AWS_SETTINGS_REGION; do
    if ! grep -q "^${key}=" "$ENV_FILE"; then
        echo "Error: $key is missing from $ENV_FILE" >&2
        exit 1
    fi
done

echo "Deploying AWS bootstrap secrets to Fly app: $APP_NAME"

{
    grep -E '^AWS_SETTINGS_(KEY_ID|ACCESS_KEY|REGION)=' "$ENV_FILE"
    printf 'AWS_SETTINGS_SECRET_NAME=%s\n' "$AWS_SECRET_NAME"
} | tr -d '\r' | fly secrets import -a "$APP_NAME"

echo "Secrets deployed. Fly has created a release with the updated values."
