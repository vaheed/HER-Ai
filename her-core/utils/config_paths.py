from __future__ import annotations

import os
from pathlib import Path


def resolve_config_file(filename: str) -> Path:
    """Return an existing config file path from common runtime locations.

    Search order:
    1. ``HER_CONFIG_DIR`` environment variable, if set.
    2. ``/app/config`` (container runtime config volume location).
    3. ``<repo>/config`` relative to this module.
    4. ``./config`` relative to current working directory.

    If no candidate exists, returns the first candidate path as a sensible default.
    """

    candidates: list[Path] = []

    env_config_dir = os.getenv("HER_CONFIG_DIR")
    if env_config_dir:
        candidates.append(Path(env_config_dir) / filename)

    candidates.extend(
        [
            Path("/app/config") / filename,
            Path(__file__).resolve().parents[2] / "config" / filename,
            Path.cwd() / "config" / filename,
        ]
    )

    for path in candidates:
        if path.exists():
            return path

    return candidates[0]

