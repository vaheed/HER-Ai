from __future__ import annotations

from fastapi import APIRouter, Query, Request

from her.models import MemorySearchResponse, SemanticMemoryItem
from her.observability.metrics import REQUEST_COUNTER

router = APIRouter()


@router.get("/memory/search", response_model=MemorySearchResponse)
async def memory_search(
    request: Request,
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
) -> MemorySearchResponse:
    """Search semantic memory by embedding similarity."""

    REQUEST_COUNTER.labels(route="memory.search").inc()
    embedding = await request.app.state.embedding_service.embed(q)
    if embedding is None:
        return MemorySearchResponse(query=q, items=[])

    try:
        records = await request.app.state.memory_store.semantic_search(
            query_embedding=embedding,
            top_k=top_k,
            min_confidence=0.0,
        )
    except Exception:
        records = []

    items = [
        SemanticMemoryItem(
            id=record.id,
            concept=record.concept,
            summary=record.summary,
            confidence=record.confidence,
            tags=record.tags,
            last_reinforced=record.last_reinforced,
        )
        for record in records
    ]
    return MemorySearchResponse(query=q, items=items)
