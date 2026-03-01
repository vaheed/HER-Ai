from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PersonalityVector(BaseModel):
    curiosity: float = Field(ge=0.1, le=0.95)
    warmth: float = Field(ge=0.1, le=0.95)
    directness: float = Field(ge=0.1, le=0.95)
    playfulness: float = Field(ge=0.1, le=0.95)
    seriousness: float = Field(ge=0.1, le=0.95)
    empathy: float = Field(ge=0.1, le=0.95)
    skepticism: float = Field(ge=0.1, le=0.95)


class EmotionalState(BaseModel):
    state: Literal["calm", "playful", "curious", "reflective", "tense", "warm"]
    intensity: float = Field(ge=0.0, le=1.0)
    decay_rate: float = 0.1
    triggered_by: Optional[str] = None


class Episode(BaseModel):
    id: UUID
    session_id: UUID
    timestamp: datetime
    content: str
    embedding: Optional[List[float]]
    emotional_valence: float
    importance_score: float
    decay_factor: float
    archived: bool
    metadata: Dict[str, str]


class LLMRequest(BaseModel):
    messages: List[Dict[str, str]]
    system_prompt: str
    max_tokens: int = 1000
    temperature: float = 0.7
    session_id: UUID
    trace_id: str


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int


class ChatRequest(BaseModel):
    content: str
    session_id: UUID


class ChatResponse(BaseModel):
    content: str
    provider: str
    model: str
    cost_usd: float
    trace_id: str


class SemanticMemoryItem(BaseModel):
    id: UUID
    concept: str
    summary: str
    confidence: float
    tags: List[str]
    last_reinforced: datetime


class MemorySearchResponse(BaseModel):
    query: str
    items: List[SemanticMemoryItem]


class GoalResponse(BaseModel):
    id: UUID
    description: str
    status: str
    priority: float
    created_at: datetime
    last_progressed: Optional[datetime]


class StateResponse(BaseModel):
    personality: PersonalityVector
    emotion: EmotionalState
    provider_priority: List[str]
    embedding_provider: str
