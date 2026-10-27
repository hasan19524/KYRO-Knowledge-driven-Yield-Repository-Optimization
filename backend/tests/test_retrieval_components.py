"""Unit tests for the ported retrieval components (Phase 3a).

Service-free (no PostgreSQL / ChromaDB / Kafka): pure ranking, context
budget and prompt logic. End-to-end behaviour through POST /api/query is
covered by tests/test_query_api.py.
"""

from __future__ import annotations

import pytest

from app import config
from app.ingest.indexer import QueryHit
from app.retrieval import (
    EMPTY_CONTEXT_NOTE,
    REFUSAL_SENTENCE,
    apply_char_budget,
    build_query_prompt,
    rank_hits,
)


def _hit(
    distance: float | None,
    *,
    commit_id: int | None = 1,
    file_id: int | None = 2,
    path: str = "src/a.py",
    status: str = "modified",
    document: str = "document body",
) -> QueryHit:
    meta: dict = {"path": path, "status": status}
    if commit_id is not None:
        meta["commit_id"] = commit_id
    if file_id is not None:
        meta["file_id"] = file_id
    return QueryHit(document=document, metadata=meta, distance=distance)


# ------------------------------------------------------------- rank_hits
def test_rank_hits_orders_by_similarity():
    hits = [
        _hit(0.9, document="doc a"),
        _hit(0.2, document="doc b"),
        _hit(0.5, document="doc c"),
    ]
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.0)
    assert [r.hit.distance for r in ranked] == [0.2, 0.5, 0.9]
    assert [round(r.similarity, 4) for r in ranked] == [0.8, 0.5, 0.1]


def test_rank_hits_drops_below_threshold():
    hits = [_hit(0.5, document="relevant"), _hit(0.95, document="noise")]
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.1)
    assert [r.hit.distance for r in ranked] == [0.5]


def test_rank_hits_similarity_safely_above_threshold_passes():
    # 1 - 0.89 = 0.11 > 0.1; exact-boundary equality is float-dependent
    # (1 - 0.9 < 0.1 in IEEE-754), so the meaningful contract is a clear
    # margin above/below.
    ranked = rank_hits(
        [_hit(0.89, document="marginal")], top_k=8, similarity_threshold=0.1
    )
    assert len(ranked) == 1
    assert ranked[0].similarity == pytest.approx(0.11)


def test_rank_hits_similarity_just_below_threshold_drops():
    ranked = rank_hits(
        [_hit(0.91, document="noise")], top_k=8, similarity_threshold=0.1
    )
    assert ranked == []


def test_rank_hits_requires_complete_metadata():
    hits = [
        _hit(0.2, document="complete"),
        _hit(0.1, commit_id=None, document="no commit id"),
        _hit(0.1, file_id=None, document="no file id"),
        _hit(0.1, commit_id=None, file_id=None, document="bare"),
    ]
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.0)
    assert len(ranked) == 1
    assert ranked[0].hit.metadata["commit_id"] == 1
    assert ranked[0].hit.metadata["file_id"] == 2


def test_rank_hits_dedup_keeps_nearest_copy():
    hits = [
        _hit(0.4, path="a.py", status="modified", document="same content"),
        _hit(0.3, path="a.py", status="modified", document="same content"),
        _hit(0.5, document="other content"),
    ]
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.0)
    assert len(ranked) == 2
    assert ranked[0].hit.distance == 0.3
    assert ranked[1].hit.document == "other content"


def test_rank_hits_dedup_frees_a_slot_for_distinct_chunks():
    # The point of over-fetching: a duplicate must not waste a top-K slot.
    hits = [
        _hit(0.1, path="a.py", status="modified", document="same content"),
        _hit(0.15, path="a.py", status="modified", document="same content"),
        _hit(0.6, document="distinct"),
    ]
    ranked = rank_hits(hits, top_k=2, similarity_threshold=0.0)
    assert len(ranked) == 2
    assert ranked[0].hit.distance == 0.1
    assert ranked[1].hit.document == "distinct"


def test_rank_hits_caps_at_top_k():
    hits = [_hit(0.1 + i * 0.01, document=f"doc {i}") for i in range(10)]
    ranked = rank_hits(hits, top_k=3, similarity_threshold=0.0)
    assert [r.hit.document for r in ranked] == ["doc 0", "doc 1", "doc 2"]


def test_rank_hits_missing_distance_is_zero_similarity():
    hits = [_hit(None, document="no distance"), _hit(0.5, document="real")]
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.1)
    assert [r.hit.distance for r in ranked] == [0.5]  # None dropped
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.0)
    assert ranked[-1].hit.distance is None  # kept, ranked last


def test_rank_hits_empty_input():
    assert rank_hits([], top_k=8, similarity_threshold=0.1) == []


# ------------------------------------------- exclude_file_ids (deleted code)
def test_rank_hits_excludes_deleted_file_ids():
    hits = [
        _hit(0.1, file_id=7, path="gone.py", document="deleted file content"),
        _hit(0.2, file_id=8, path="live.py", document="current file content"),
    ]
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.0, exclude_file_ids={7})
    assert [r.hit.metadata["path"] for r in ranked] == ["live.py"]


def test_rank_hits_exclusion_frees_a_top_k_slot():
    # Exclusion happens before the cap: a deleted hit must not crowd a
    # current-code hit out of the top-K window.
    hits = [
        _hit(0.1, file_id=7, path="gone.py", document="deleted (nearest)"),
        _hit(0.2, file_id=8, path="a.py", document="current a"),
        _hit(0.3, file_id=9, path="b.py", document="current b"),
    ]
    ranked = rank_hits(hits, top_k=2, similarity_threshold=0.0, exclude_file_ids={7})
    assert [r.hit.metadata["path"] for r in ranked] == ["a.py", "b.py"]


def test_rank_hits_exclusion_of_everything_yields_empty():
    hits = [_hit(0.1, file_id=7, document="only deleted content")]
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.0, exclude_file_ids={7})
    assert ranked == []


def test_rank_hits_no_exclusion_set_keeps_behaviour():
    hits = [_hit(0.1, file_id=7, document="kept when no exclusion")]
    ranked = rank_hits(hits, top_k=8, similarity_threshold=0.0)
    assert len(ranked) == 1
    # Explicitly empty set is also a no-op.
    assert (
        len(rank_hits(hits, top_k=8, similarity_threshold=0.0, exclude_file_ids=set()))
        == 1
    )


# ------------------------------------------------------- apply_char_budget
def test_budget_keeps_everything_that_fits():
    blocks = ["aaa", "bbb", "ccc"]
    assert apply_char_budget(blocks, max_chars=100) == [
        (0, "aaa"),
        (1, "bbb"),
        (2, "ccc"),
    ]


def test_budget_stops_when_over_half_consumed():
    # 300 of 500 consumed (>= half) -> no truncation attempt, clean stop.
    blocks = ["x" * 300, "y" * 300]
    kept = apply_char_budget(blocks, max_chars=500)
    assert kept == [(0, "x" * 300)]


def test_budget_truncates_tail_under_half_consumed():
    # 100 of 500 consumed (< half), remaining 400 > 200 -> partial include.
    blocks = ["x" * 100, "y" * 1000]
    kept = apply_char_budget(blocks, max_chars=500)
    assert len(kept) == 2
    index, block = kept[1]
    assert index == 1
    assert block == "y" * 400 + "..."
    assert len(block) == 403


def test_budget_skips_tail_when_remainder_too_small():
    # 120 of 300 consumed (< half), remaining 180 <= 200 -> nothing kept.
    blocks = ["x" * 120, "y" * 500]
    kept = apply_char_budget(blocks, max_chars=300)
    assert kept == [(0, "x" * 120)]


def test_budget_empty_input():
    assert apply_char_budget([], max_chars=500) == []


def test_budget_returns_original_indices():
    # Indices stay aligned with the input so references can be matched up.
    blocks = ["a" * 10, "b" * 10, "c" * 10, "d" * 10]
    kept = apply_char_budget(blocks, max_chars=25)
    assert [i for i, _ in kept] == [0, 1]


# ----------------------------------------------------------------- prompt
def test_prompt_contains_identity_repository_and_question():
    prompt = build_query_prompt(
        repository="acme/widgets",
        context="commit abc123: fixed retry",
        question="How does retry work?",
    )
    assert "KYRO" in prompt
    assert "acme/widgets" in prompt
    assert "How does retry work?" in prompt
    assert "commit abc123: fixed retry" in prompt


def test_prompt_grounding_rules():
    prompt = build_query_prompt(repository="r", context="ctx", question="q")
    assert "ONLY the repository context" in prompt
    assert "do not invent facts" in prompt
    assert REFUSAL_SENTENCE in prompt
    assert "cite commit shas and file paths" in prompt


def test_empty_context_note_is_stable():
    # The query API contract surfaces this exact note in the prompt when
    # retrieval yields nothing; keep it locked.
    assert EMPTY_CONTEXT_NOTE == (
        "No indexed changes matched this question for this repository."
    )


# ----------------------------------------------------------------- config
def test_query_config_defaults_are_sane():
    assert config.QUERY_RETRIEVAL_OVERFETCH >= 1
    assert 0.0 <= config.QUERY_SIMILARITY_THRESHOLD <= 1.0
