"""Query retrieval components ported from Maaz's RAG deliverable (Phase 3a).

Scope: ranking/threshold/de-duplication, bounded context assembly and the
grounded prompt only. Ingestion, the Chroma collection and embedding
configuration, PostgreSQL enrichment and the /api/query response contract
are unchanged.
"""

from app.retrieval.prompt import (
    EMPTY_CONTEXT_NOTE,
    REFUSAL_SENTENCE,
    build_query_prompt,
)
from app.retrieval.ranking import RankedHit, apply_char_budget, rank_hits

__all__ = [
    "EMPTY_CONTEXT_NOTE",
    "REFUSAL_SENTENCE",
    "RankedHit",
    "apply_char_budget",
    "build_query_prompt",
    "rank_hits",
]
