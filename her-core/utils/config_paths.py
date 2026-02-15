from __future__ import annotations

import os
from pathlib import Path


def resolve_config_file(filename: str) -> Path:
    """Return an existing config file path from common runtime locations.

    Search order:
    1. ``HER_CONFIG_DIR`` environment variable, if set.
    2. ``/app/config`` (container runtime config volume location).
    3. ``/app/config.defaults`` (image-baked defaults).
    4. ``<repo>/config`` relative to this module.
    5. ``./config`` relative to current working directory.

    If no candidate exists, returns the first candidate path as a sensible default.
    """

    candidates: list[Path] = []

    env_config_dir = os.getenv("HER_CONFIG_DIR")
    if env_config_dir:
        candidates.append(Path(env_config_dir) / filename)

    # In container runtimes where /app/config is mounted but not writable by appuser,
    # prefer baked defaults to avoid stale, unseeded runtime volumes.
    runtime_config_dir = Path("/app/config")
    defaults_config_dir = Path("/app/config.defaults")
    prefer_defaults = runtime_config_dir.exists() and not os.access(runtime_config_dir, os.W_OK)

    container_candidates: list[Path]
    if prefer_defaults:
        container_candidates = [
            defaults_config_dir / filename,
            runtime_config_dir / filename,
        ]
    else:
        container_candidates = [
            runtime_config_dir / filename,
            defaults_config_dir / filename,
        ]

    candidates.extend(
        [
            *container_candidates,
            Path(__file__).resolve().parents[2] / "config" / filename,
            Path.cwd() / "config" / filename,
        ]
    )

    for path in candidates:
        if path.exists():
            return path

    # Prefer a stable local path for callers that create or inspect configs
    # when no candidate exists yet.
    return Path(__file__).resolve().parents[2] / "config" / filename
