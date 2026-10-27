"""Ranking, thresholding and de-duplication over Chroma query hits.

Adapted from Maaz's retrieval service and his ranking service:

* similarity = 1 - distance (the kyro_changes collection is cosine space;
  verified empirically against this cluster before porting)
* a similarity floor drops obviously-unrelated noise before it can reach
  the LLM context
* duplicate copies of identical content keep only the nearest one, and the
  top-K cap is applied AFTER de-duplication so duplicates cannot crowd
  distinct chunks out of the window (the point of over-fetching in the
  query call)
* a character budget bounds the assembled context; a partially-useful
  tail block is truncated instead of discarded when less than half the
  budget has been consumed

Only pure functions live here — no Chroma/PG/network access — so the
logic is unit-testable without services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.ingest.indexer import QueryHit


@dataclass(frozen=True)
class RankedHit:
    """A hit that passed filtering, with its cosine similarity."""

    hit: QueryHit
    similarity: float


def _similarity(distance: float | None) -> float:
    # Cosine distance: 0.0 = identical, 2.0 = opposite. A missing distance
    # carries no evidence and is treated as similarity 0.0 (dropped by any
    # positive threshold).
    return 1.0 - distance if distance is not None else 0.0


def rank_hits(
    hits: Sequence[QueryHit],
    *,
    top_k: int,
    similarity_threshold: float,
    exclude_file_ids: set[int] | None = None,
) -> list[RankedHit]:
    """Best-first, thresholded, de-duplicated top-K of complete hits.

    * only hits with complete PostgreSQL references (commit_id + file_id in
      metadata) are eligible — enrichment cannot succeed without them
    * hits whose ``file_id`` is in ``exclude_file_ids`` are dropped before the
      top-K cap, so deleted/renamed files cannot crowd current code out of the
      window (PostgreSQL ``files.is_deleted`` is the source of truth; see the
      query handler)
    * hits with similarity < `similarity_threshold` are dropped (equal to
      the threshold passes)
    * identical (path, status, document) copies keep the nearest one
    * the final list is capped at `top_k`, after de-duplication
    """
    excluded = exclude_file_ids or set()
    candidates: list[RankedHit] = []
    for hit in hits:
        meta = hit.metadata or {}
        if meta.get("commit_id") is None or meta.get("file_id") is None:
            continue
        if int(meta["file_id"]) in excluded:
            continue
        similarity = _similarity(hit.distance)
        if similarity < similarity_threshold:
            continue
        candidates.append(RankedHit(hit=hit, similarity=similarity))

    # Stable sort: ties keep Chroma's own (distance ascending) order.
    candidates.sort(key=lambda ranked: -ranked.similarity)

    seen: set[tuple] = set()
    ranked: list[RankedHit] = []
    for candidate in candidates:
        if len(ranked) >= top_k:
            break
        meta = candidate.hit.metadata
        key = (meta.get("path"), meta.get("status"), candidate.hit.document)
        if key in seen:
            continue
        seen.add(key)
        ranked.append(candidate)
    return ranked


def apply_char_budget(
    blocks: Sequence[str], *, max_chars: int
) -> list[tuple[int, str]]:
    """Keep a prefix of context blocks within a character budget.

    A block that fits is kept whole. The first block that overflows ends
    the loop, except when less than half the budget has been consumed and
    a meaningful remainder (> 200 chars) exists: then the block is
    truncated to the remainder so the model still sees its beginning.

    Returns (original_index, block) pairs so callers can align side
    outputs — e.g. API references — with what actually reached the LLM.
    """
    total = 0
    kept: list[tuple[int, str]] = []
    for index, block in enumerate(blocks):
        if total + len(block) <= max_chars:
            kept.append((index, block))
            total += len(block)
        elif total < max_chars // 2:
            remaining = max_chars - total
            if remaining > 200:
                kept.append((index, block[:remaining] + "..."))
                total += remaining
            break
        else:
            break
    return kept
