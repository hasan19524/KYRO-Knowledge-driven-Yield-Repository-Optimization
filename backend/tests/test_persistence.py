"""PostgreSQL persistence tests (§19-§24, §35-§37, §61 C-G/Q).

Covers: first commit snapshot, chronological history, added/modified/
deleted/renamed files, exact current content, historical commit_files
preservation, out-of-order guard, and duplicate protection.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Commit,
    CommitFile,
    File,
    IngestionEvent,
    Repository,
    RepositoryStatus,
)
from tests.conftest import (
    apply_event,
    build_backfill_events,
    live_event_for_head,
)


def _counts(db):
    with db() as session:
        return {
            "commits": session.scalar(select(func.count()).select_from(Commit)),
            "files": session.scalar(select(func.count()).select_from(File)),
            "commit_files": session.scalar(
                select(func.count()).select_from(CommitFile)
            ),
        }


def _file(db, path: str, github_id: int = 1395956448):
    with db() as session:
        repo = session.scalar(
            select(Repository).where(Repository.github_repository_id == github_id)
        )
        return session.scalar(
            select(File).where(File.repository_id == repo.id, File.path == path)
        )


def _commit_files(db, sha: str):
    with db() as session:
        commit = session.scalar(select(Commit).where(Commit.github_commit_sha == sha))
        assert commit is not None, f"commit {sha} missing"
        rows = session.execute(
            select(CommitFile, File)
            .join(File, File.id == CommitFile.file_id)
            .where(CommitFile.commit_id == commit.id)
        ).all()
        return {f.path: cf for cf, f in rows}, commit


# ----------------------------------------------------------------- §61.C
def test_first_commit_is_initial_snapshot(processor_env):
    """§8/§37: before=null, every file status=added, content stored."""
    fake = processor_env.fake
    c1 = fake.push("initial commit", {"README.md": "# KYRO\n", "app.py": "print(1)\n"})
    events = build_backfill_events(fake)
    assert len(events) == 1
    evt = events[0]
    assert evt["push"]["before"] is None
    assert evt["push"]["after"] == c1
    assert evt["backfill"]["is_initial_commit"] is True

    outcome = apply_event(processor_env.processor, evt)
    assert outcome.value == "processed"

    by_path, commit = _commit_files(processor_env.db, c1)
    assert commit.parent_sha is None
    assert set(by_path) == {"README.md", "app.py"}
    assert all(cf.status == "added" for cf in by_path.values())
    readme = _file(processor_env.db, "README.md")
    assert readme.current_content == "# KYRO\n"
    assert readme.current_content_commit_sha == c1
    assert readme.is_deleted is False


# ----------------------------------------------------------------- §61.D
def test_multiple_historical_commits_chronological(processor_env):
    """§6: one event per commit, parents before children, chain persisted."""
    fake = processor_env.fake
    c1 = fake.push("init", {"a.py": "v1\n"})
    c2 = fake.push("change a", {"a.py": "v2\n", "b.py": "b1\n"})
    c3 = fake.push("add c", {"c.py": "c1\n"})

    events = build_backfill_events(fake)
    shas = [e["push"]["after"] for e in events]
    assert shas == [c1, c2, c3]  # chronological (parents first)
    assert [e["backfill"]["sequence"] for e in events] == [0, 1, 2]

    for i, evt in enumerate(events):
        assert apply_event(processor_env.processor, evt, offset=i).value == "processed"

    with processor_env.db() as session:
        rows = session.scalars(
            select(Commit).where(
                Commit.repository_id.in_(
                    select(Repository.id).where(
                        Repository.github_repository_id == 1395956448
                    )
                )
            )
        ).all()
        by_sha = {r.github_commit_sha: r for r in rows}
        assert len(by_sha) == 3
        assert by_sha[c2].parent_sha == c1
        assert by_sha[c3].parent_sha == c2
        assert by_sha[c1].message == "init"
        assert by_sha[c2].committed_at is not None

    a_file = _file(processor_env.db, "a.py")
    # exact current content from the NEWEST commit (§24)
    assert a_file.current_content == "v2\n"
    assert a_file.current_content_commit_sha == c2


# ------------------------------------------------------- §61.E/F modified+added
def test_modified_and_added_files(processor_env):
    fake = processor_env.fake
    c1 = fake.push("init", {"auth.py": "def check():\n    return True\n"})
    c2 = fake.push(
        "harden auth",
        {"auth.py": "def check():\n    return False\n", "util.py": "U = 1\n"},
    )
    events = build_backfill_events(fake)
    for i, e in enumerate(events):
        apply_event(processor_env.processor, e, offset=i)

    by_path2, _ = _commit_files(processor_env.db, c2)
    assert by_path2["auth.py"].status == "modified"
    assert by_path2["util.py"].status == "added"
    assert by_path2["auth.py"].additions >= 1

    # Historical record for c1 preserved (§23/§24)
    by_path1, _ = _commit_files(processor_env.db, c1)
    assert by_path1["auth.py"].status == "added"
    assert by_path1["auth.py"].patch is not None

    auth = _file(processor_env.db, "auth.py")
    assert auth.current_content == "def check():\n    return False\n"
    assert auth.current_content_commit_sha == c2
    util = _file(processor_env.db, "util.py")
    assert util.current_content == "U = 1\n"


# ----------------------------------------------------------------- §61.G
def test_deleted_file(processor_env):
    fake = processor_env.fake
    fake.push("init", {"gone.py": "x = 1\n", "stay.py": "y = 2\n"})
    c2 = fake.push("remove gone", {"gone.py": None})
    events = build_backfill_events(fake)
    for i, e in enumerate(events):
        apply_event(processor_env.processor, e, offset=i)

    by_path, _ = _commit_files(processor_env.db, c2)
    assert by_path["gone.py"].status == "deleted"

    gone = _file(processor_env.db, "gone.py")
    assert gone.is_deleted is True
    assert gone.current_content is None
    # history preserved: c1 still shows the file existed
    by_path1, _ = _commit_files(processor_env.db, fake.commits[0].sha)
    assert by_path1["gone.py"].status == "added"

    stay = _file(processor_env.db, "stay.py")
    assert stay.is_deleted is False
    assert stay.current_content == "y = 2\n"


# ----------------------------------------------------------------- §61.H
def test_rename_via_backfill(processor_env):
    """Rename carries previous_path (backfill schema); old path retired."""
    fake = processor_env.fake
    fake.push("init", {"old_name.py": "VALUE = 1\n"})
    c2 = fake.push(
        "rename file",
        {"new_name.py": "VALUE = 1\n"},
        renames={"new_name.py": "old_name.py"},
    )
    events = build_backfill_events(fake)
    assert events[1]["changes"][0]["previous_path"] == "old_name.py"
    assert events[1]["changes"][0]["status"] == "renamed"
    for i, e in enumerate(events):
        apply_event(processor_env.processor, e, offset=i)

    by_path, _ = _commit_files(processor_env.db, c2)
    assert by_path["new_name.py"].status == "renamed"
    assert by_path["new_name.py"].previous_path == "old_name.py"
    # the old path is retired in the same commit (§35)
    assert by_path["old_name.py"].status == "deleted"

    new = _file(processor_env.db, "new_name.py")
    old = _file(processor_env.db, "old_name.py")
    assert new.current_content == "VALUE = 1\n"
    assert new.is_deleted is False
    assert old.is_deleted is True
    assert old.current_content is None


# ----------------------------------------------------------------- §61.Q
def test_duplicate_event_is_idempotent(processor_env):
    fake = processor_env.fake
    fake.push("init", {"a.py": "1\n"})
    fake.push("second", {"a.py": "2\n"})
    events = build_backfill_events(fake)

    assert (
        apply_event(processor_env.processor, events[0], offset=0).value == "processed"
    )
    before = _counts(processor_env.db)

    # Kafka redelivery of the same event (same event.id)
    assert (
        apply_event(processor_env.processor, events[0], offset=0).value == "duplicate"
    )
    after = _counts(processor_env.db)
    assert before == after

    # and re-processing via direct apply_payload must not duplicate rows either
    assert (
        apply_event(processor_env.processor, events[0], offset=7).value == "duplicate"
    )

    with processor_env.db() as session:
        n = session.scalar(select(func.count()).select_from(IngestionEvent))
        assert n == 1  # one durable ingestion_events row for that event.id


def test_database_unique_constraints(processor_env):
    """Unique constraints are enforced at the database level (§29)."""
    fake = processor_env.fake
    sha = fake.push("init", {"a.py": "1\n"})
    events = build_backfill_events(fake)
    apply_event(processor_env.processor, events[0])

    with processor_env.db() as session:
        repo = session.scalar(select(Repository).limit(1))
        with pytest.raises(IntegrityError):
            session.add(
                Commit(
                    repository_id=repo.id,
                    github_commit_sha=sha,
                    message="duplicate",
                )
            )
            session.flush()
        session.rollback()

        # files unique on (repository_id, path)
        with pytest.raises(IntegrityError):
            session.add(File(repository_id=repo.id, path="a.py"))
            session.flush()
        session.rollback()


# ---------------------------------------------------------- out-of-order §22
def test_current_content_never_regresses(processor_env):
    """An older commit arriving late must not overwrite newer content."""
    fake = processor_env.fake
    c1 = fake.push("old", {"a.py": "OLD\n"})
    fake.push("new", {"a.py": "NEW\n"})
    events = build_backfill_events(fake)
    apply_event(processor_env.processor, events[1])  # newer first
    a = _file(processor_env.db, "a.py")
    assert a.current_content == "NEW\n"

    # Now apply the OLDER event (simulates out-of-order delivery)
    apply_event(processor_env.processor, events[0])
    a = _file(processor_env.db, "a.py")
    assert a.current_content == "NEW\n"  # guard held
    assert a.current_content_commit_sha != c1
    # but the older commit's own record exists
    by_path, _ = _commit_files(processor_env.db, c1)
    assert by_path["a.py"].status == "added"


# ------------------------------------------------------- live event shape
def test_live_event_ingests_commits_and_changes(processor_env):
    """§17/§58: worker processes the event as-is (no GitHub Compare).

    The event is built from REAL fake-GitHub history so blob SHAs, patches
    and content refs are exactly what GitHub would send.
    """
    fake = processor_env.fake
    c1 = fake.push("base", {"auth.py": "def check():\n    return True\n"})
    c2 = fake.push(
        "harden auth",
        {"auth.py": "def check():\n    return False\n", "new.py": "hello\n"},
    )
    evt = live_event_for_head(fake, delivery_id=str(uuid.uuid4()))

    # Repo must already be READY, else live events defer (§15) - see
    # test_processor_idempotency for the deferral path itself.
    with processor_env.db() as session, session.begin():
        session.add(
            Repository(
                github_repository_id=1395956448,
                name="kyro-demo",
                full_name="acme/kyro-demo",
                owner="acme",
                default_branch="main",
                github_installation_id=791001,
                status=RepositoryStatus.READY.value,
            )
        )

    outcome = apply_event(processor_env.processor, evt, topic="kyro.github.push")
    assert outcome.value == "processed"

    by_path, commit = _commit_files(processor_env.db, c2)
    assert commit.parent_sha == c1
    assert by_path["auth.py"].status == "modified"
    assert by_path["new.py"].status == "added"
    # content resolved without any Compare call (§58): patch for the added
    # file, exact fetch at ref for the modified one.
    assert _file(processor_env.db, "new.py").current_content == "hello\n"
    auth = _file(processor_env.db, "auth.py")
    assert auth.current_content == "def check():\n    return False\n"
    assert auth.current_content_commit_sha == c2

    with processor_env.db() as session:
        repo = session.scalar(select(Repository).limit(1))
        assert repo.github_repository_id == 1395956448
        assert repo.status == RepositoryStatus.READY.value  # unchanged
