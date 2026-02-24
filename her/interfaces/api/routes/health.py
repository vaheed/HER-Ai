from __future__ import annotations

from datetime import datetime
from typing import Dict

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> Dict[str, str]:
    """Return service health snapshot."""

    return {"status": "ok", "time": datetime.utcnow().isoformat()}
