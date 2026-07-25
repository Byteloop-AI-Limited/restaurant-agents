"""Single-worker Fly.io Gunicorn configuration."""

import os

host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8080")
bind = os.getenv("BIND", f"{host}:{port}")
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
worker_class = os.getenv("WORKER_CLASS", "uvicorn_worker.UvicornWorker")
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", "290"))
timeout = int(os.getenv("TIMEOUT", "600"))
keepalive = int(os.getenv("KEEP_ALIVE", "5"))
loglevel = os.getenv("LOG_LEVEL", "info")
accesslog = os.getenv("ACCESS_LOG", "-") or None
errorlog = os.getenv("ERROR_LOG", "-") or None
capture_output = True
preload_app = False
worker_tmp_dir = "/dev/shm"

if workers != 1:
    raise ValueError(
        "Restaurant agents are deployed as one worker per Fly Machine; "
        f"received WEB_CONCURRENCY={workers}."
    )
