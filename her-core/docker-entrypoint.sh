#!/usr/bin/env bash
set -euo pipefail

DEFAULT_CONFIG_DIR="/app/config.defaults"
RUNTIME_CONFIG_DIR="/app/config"

mkdir -p "$RUNTIME_CONFIG_DIR"

if [ -n "${TZ:-}" ] && [ -f "/usr/share/zoneinfo/$TZ" ]; then
  ln -sf "/usr/share/zoneinfo/$TZ" /etc/localtime
  echo "$TZ" > /etc/timezone
fi

if [ -d "$DEFAULT_CONFIG_DIR" ]; then
  # Seed missing config files into the runtime volume without overwriting user edits.
  # Some Docker setups create /app/config as a root-owned mount, which is not
  # writable by the non-root app user.
  if [ -w "$RUNTIME_CONFIG_DIR" ]; then
    cp -rn "$DEFAULT_CONFIG_DIR"/. "$RUNTIME_CONFIG_DIR"/
    export HER_CONFIG_DIR="$RUNTIME_CONFIG_DIR"
  else
    echo "[entrypoint] Runtime config dir '$RUNTIME_CONFIG_DIR' is not writable; skipping seed copy and using defaults fallback." >&2
    export HER_CONFIG_DIR="$DEFAULT_CONFIG_DIR"
  fi
elif [ -d "$RUNTIME_CONFIG_DIR" ]; then
  export HER_CONFIG_DIR="$RUNTIME_CONFIG_DIR"
fi

exec "$@"
