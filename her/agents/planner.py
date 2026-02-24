from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict
from uuid import UUID, uuid4


@dataclass
class Goal:
    id: UUID
    description: str
    status: str
    created_at: datetime


class PlannerAgent:
    """Minimal goal planner and tracker."""

    def __init__(self) -> None:
        self._goals: Dict[UUID, Goal] = {}

    async def create_goal(self, description: str) -> Goal:
        """Create and store a new active goal."""

        goal = Goal(id=uuid4(), description=description, status="active", created_at=datetime.utcnow())
        self._goals[goal.id] = goal
        return goal
