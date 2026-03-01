from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID, uuid4

from her.memory.store import MemoryStore
from her.memory.types import GoalRecord


@dataclass
class Goal:
    id: UUID
    description: str
    status: str
    created_at: datetime


class PlannerAgent:
    """Minimal goal planner and tracker."""

    def __init__(self, memory_store: Optional[MemoryStore] = None) -> None:
        self._goals: Dict[UUID, Goal] = {}
        self._memory_store = memory_store

    async def create_goal(self, description: str) -> Goal:
        """Create and store a new active goal."""

        if self._memory_store is not None:
            db_goal: GoalRecord = await self._memory_store.create_goal(description=description)
            return Goal(
                id=db_goal.id,
                description=db_goal.description,
                status=db_goal.status,
                created_at=db_goal.created_at,
            )

        goal = Goal(id=uuid4(), description=description, status="active", created_at=datetime.utcnow())
        self._goals[goal.id] = goal
        return goal
