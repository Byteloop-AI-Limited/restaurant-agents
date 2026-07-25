#!/bin/sh
set -eu

if [ -z "${APP_MODULE:-}" ]; then
    echo "Error: APP_MODULE must name the selected restaurant entrypoint." >&2
    exit 1
fi

export GUNICORN_CONF="${GUNICORN_CONF:-/app/gunicorn_conf.py}"
export WORKER_CLASS="${WORKER_CLASS:-uvicorn_worker.UvicornWorker}"

echo "Starting ${APP_MODULE} on port ${PORT:-8080}"
exec gunicorn -k "$WORKER_CLASS" -c "$GUNICORN_CONF" "$APP_MODULE"
