from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query, Request

from her.models import GoalResponse
from her.observability.metrics import REQUEST_COUNTER

router = APIRouter()


@router.get("/goals", response_model=List[GoalResponse])
async def list_goals(request: Request, limit: int = Query(10, ge=1, le=100)) -> List[GoalResponse]:
    """Return active goals."""

    REQUEST_COUNTER.labels(route="goals").inc()
    try:
        goals = await request.app.state.memory_store.list_active_goals(limit=limit)
    except Exception:
        return []

    return [
        GoalResponse(
            id=goal.id,
            description=goal.description,
            status=goal.status,
            priority=goal.priority,
            created_at=goal.created_at,
            last_progressed=goal.last_progressed,
        )
        for goal in goals
    ]
