#!/bin/sh
set -eu

usage() {
    echo "Usage: $0 --app {bnat|sfcs} [extra fly deploy args...]" >&2
}

if [ "$#" -lt 2 ] || [ "$1" != "--app" ]; then
    usage
    exit 2
fi

app="$2"
shift 2

case "$app" in
    bnat)
        app_package="bnat-agent"
        ;;
    sfcs)
        app_package="sfcs-agent"
        ;;
    *)
        usage
        exit 2
        ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$project_root"

if ! command -v fly >/dev/null 2>&1; then
    echo "Error: flyctl is not installed or is not on PATH." >&2
    exit 1
fi

exec fly deploy . \
    --config "apps/$app/fly.toml" \
    --build-arg "APP_PACKAGE=$app_package" \
    --ha=false \
    "$@"
