#!/usr/bin/env bash
set -euo pipefail

DEFAULT_CONFIG_DIR="/app/config.defaults"
RUNTIME_CONFIG_DIR="/app/config"

mkdir -p "$RUNTIME_CONFIG_DIR"

if [ -d "$DEFAULT_CONFIG_DIR" ]; then
  # Seed missing config files into the runtime volume without overwriting user edits.
  cp -rn "$DEFAULT_CONFIG_DIR"/. "$RUNTIME_CONFIG_DIR"/
fi

exec "$@"
