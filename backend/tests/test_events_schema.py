"""Event contract tests (§9): live n8n payload + backfill classification."""

from __future__ import annotations

import json
import uuid

import pytest

from app.schemas.events import (
    CLASSIFICATION_BACKFILL,
    CLASSIFICATION_LIVE,
    EventValidationError,
    parse_event,
)
from tests.conftest import live_event


def test_parse_live_event_matching_n8n_contract():
    """The exact shape produced by n8n workflow mlEODTybeNYN2wzq parses."""
    payload = live_event(
        delivery_id=str(uuid.uuid4()),
        before="a" * 40,
        after="b" * 40,
        commits=[
            {
                "sha": "b" * 40,
                "message": "fix: token expiry",
                "timestamp": "2025-01-01T10:00:00Z",
                "author": {"name": "Alice", "email": "a@x.com", "username": None},
                "committer": {"name": "Alice", "email": "a@x.com", "username": None},
                "added": ["src/new.py"],
                "modified": ["src/auth.py"],
                "removed": [],
            }
        ],
        changes=[
            {
                "path": "src/auth.py",
                "status": "modified",
                "additions": 3,
                "deletions": 1,
                "changes": 4,
                "sha": "c" * 40,
                "patch": "@@ -1,3 +1,5 @@\n a\n-b\n+c\n+d\n e",
            }
        ],
    )
    evt = parse_event(json.dumps(payload))
    assert evt.event.classification == CLASSIFICATION_LIVE
    assert not evt.is_backfill
    assert evt.repository.github_id == 1395956448
    assert evt.push.after == "b" * 40
    assert evt.commits[0].added == ["src/new.py"]
    assert evt.changes[0].path == "src/auth.py"
    assert evt.installation.github_installation_id == 791001


def test_parse_backfill_event_requires_classification():
    payload = live_event(delivery_id="x", after="d" * 40, commits=[])
    payload["event"]["classification"] = CLASSIFICATION_BACKFILL
    with pytest.raises(EventValidationError):
        parse_event(payload)  # classification without backfill block


def test_backfill_block_forces_classification():
    payload = live_event(delivery_id="x", after="d" * 40)
    payload["backfill"] = {
        "sequence": 0,
        "is_initial_commit": True,
        "parent_sha": None,
        "sync_target_commit": "d" * 40,
    }
    with pytest.raises(EventValidationError):
        parse_event(payload)  # backfill block without classification
    payload["event"]["classification"] = CLASSIFICATION_BACKFILL
    evt = parse_event(payload)
    assert evt.is_backfill
    assert evt.backfill is not None
    assert evt.backfill.is_initial_commit


def test_invalid_json_rejected():
    with pytest.raises(EventValidationError):
        parse_event(b"{not json")


def test_missing_required_fields_rejected():
    payload = live_event(delivery_id="x")
    del payload["repository"]
    with pytest.raises(EventValidationError):
        parse_event(payload)


def test_empty_event_id_rejected():
    payload = live_event(delivery_id="   ")
    with pytest.raises(EventValidationError):
        parse_event(payload)
