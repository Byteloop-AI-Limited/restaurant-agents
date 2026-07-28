#!/bin/sh
set -eu

envLoad() {
    export $(cat .env | xargs)
}

usage() {
    echo "Usage: $0 --app {bnat|sfcs}" >&2
}

if [ "$#" -ne 2 ] || [ "$1" != "--app" ]; then
    usage
    exit 2
fi

case "$2" in
    bnat)
        app_package="bnat-agent"
        app_module="bnat_agent.main:app"
        ;;
    sfcs)
        app_package="sfcs-agent"
        app_module="sfcs_agent.main:app"
        ;;
    *)
        usage
        exit 2
        ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$project_root"

envLoad

exec uv run --package "$app_package" uvicorn "$app_module" \
    --host 127.0.0.1 \
    --port 3101 \
    --reload
