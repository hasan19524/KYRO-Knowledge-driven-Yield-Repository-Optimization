"""Shared fixtures: PostgreSQL (kyro_test), ChromaDB, Kafka, worker harness.

Safety: every test runs against the dedicated `kyro_test` database (created
on demand, migrated with the project's Alembic revision). The real `kyro`
database and the real `kyro.github.*` topics are never touched - Kafka tests
use per-test unique topics that are deleted afterwards.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine, text

if TYPE_CHECKING:
    from tests.fake_github import FakeGitHub

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DB_URL = "postgresql+psycopg://kyro:kyro@localhost:5433/kyro_test"
ADMIN_DB_URL = "postgresql+psycopg://kyro:kyro@localhost:5433/postgres"
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
CHROMA_URL = os.environ.get("CHROMA_URL", "http://localhost:8100")

ADMIN_TABLES = (
    "commit_files,commits,files,github_installations,"
    "ingestion_events,repositories,users,alembic_version"
)


# --------------------------------------------------------------- database
@pytest.fixture(scope="session")
def session_factory():
    """Recreate kyro_test from scratch, run the real Alembic migration."""
    from app.db import reset_engine

    reset_engine()  # drop any cached engine holding connections

    admin = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        try:
            conn.execute(text("DROP DATABASE IF EXISTS kyro_test WITH (FORCE)"))
        except Exception:
            conn.execute(text("DROP DATABASE IF EXISTS kyro_test"))
        conn.execute(text("CREATE DATABASE kyro_test"))
    admin.dispose()

    env = dict(os.environ)
    env["DATABASE_URL"] = TEST_DB_URL
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{proc.stdout}\n{proc.stderr}")

    # Verify the schema actually landed before any test runs.
    probe = create_engine(TEST_DB_URL)
    with probe.connect() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename = 'repositories'"
            )
        ).scalar()
    probe.dispose()
    if n != 1:
        raise RuntimeError("alembic upgrade did not create the repositories table")

    from app.db import get_session_factory

    factory = get_session_factory(TEST_DB_URL)
    yield factory

    # Session teardown: drop everything in kyro_test only.
    from app.db import Base, get_engine

    engine = get_engine()
    assert "kyro_test" in str(engine.url), "refusing to drop non-test database"
    Base.metadata.drop_all(engine)
    reset_engine()


@pytest.fixture
def db(session_factory):
    """Session factory with a clean database for each test."""
    yield session_factory
    from app.db import Base, get_engine

    engine = get_engine()
    assert "kyro_test" in str(engine.url)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


def clean_tables(session_factory) -> None:
    from app.db import Base, get_engine

    engine = get_engine()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


# --------------------------------------------------------------- chroma
@pytest.fixture
def indexer():
    """Real ChromaDB index in a unique per-test collection."""
    from app.ingest.indexer import ChromaIndexer

    name = f"kyro_test_{uuid.uuid4().hex[:12]}"
    idx = ChromaIndexer(url=CHROMA_URL, collection_name=name)
    yield idx
    idx.reset()


@pytest.fixture
def failing_indexer(indexer):
    """Indexer wrapper whose Chroma writes fail on demand (retry tests)."""

    class FailingIndexer:
        def __init__(self) -> None:
            self.fail = False
            self.calls = 0
            self.real = indexer

        def index_event(self, items):
            self.calls += 1
            if self.fail:
                from app.ingest.indexer import IndexError_

                raise IndexError_("chroma upsert failed: injected failure")
            return self.real.index_event(items)

        def __getattr__(self, item):
            return getattr(self.real, item)

    return FailingIndexer()


# --------------------------------------------------------------- kafka
@pytest.fixture
def kafka_topics():
    """Per-test unique live/backfill topics (5 partitions, RF=1)."""
    from confluent_kafka.admin import (
        AdminClient,
        NewTopic,  # pyright: ignore[reportPrivateImportUsage]
    )

    admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})
    suffix = uuid.uuid4().hex[:10]
    topics = {
        "live": f"kyro.test.push.{suffix}",
        "backfill": f"kyro.test.backfill.{suffix}",
    }
    futures = admin.create_topics(
        [NewTopic(t, num_partitions=5, replication_factor=1) for t in topics.values()]
    )
    for fut in futures.values():
        try:
            fut.result()
        except Exception as exc:  # pragma: no cover
            if "already exists" not in str(exc).lower():
                raise
    time.sleep(0.3)
    yield SimpleNamespace(**topics)
    futures = admin.delete_topics(list(topics.values()))
    for fut in futures.values():
        with contextlib.suppress(Exception):  # pragma: no cover
            fut.result()


@pytest.fixture
def producer_factory():
    """BackfillProducer factory bound to the current test topics."""
    from app.kafka.producer import BackfillProducer

    created = []

    def make(topic: str | None = None):
        p = BackfillProducer(
            bootstrap=KAFKA_BOOTSTRAP, client_id=f"kyro-test-{uuid.uuid4().hex[:6]}"
        )
        created.append(p)
        return p

    yield make
    for p in created:
        p.close()


# ------------------------------------------------------- worker harness
class WorkerHarness:
    """Drives one IngestionWorker deterministically inside tests."""

    def __init__(self, processor, topics: list[str], group_id: str) -> None:
        from app.kafka.consumer import IngestionWorker

        self.processor = processor
        self.worker = IngestionWorker(
            processor,
            bootstrap=KAFKA_BOOTSTRAP,
            group_id=group_id,
            topics=topics,
            client_id=f"kyro-test-worker-{uuid.uuid4().hex[:6]}",
        )
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        """Background drain loop (for running alongside the sync manager)."""
        self.worker.start()

        def _loop() -> None:
            while not self._stop.is_set():
                self.worker.poll_once(num_messages=50, timeout_s=0.2)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def drain(
        self,
        *,
        expected: int | None = None,
        max_rounds: int = 300,
        timeout_s: float = 30.0,
    ) -> int:
        """Poll until the topics are quiet (or `expected` messages seen).

        First waits for the asynchronous partition assignment (subscribe is
        async - giving up before assignment looks like 'nothing processed').
        With `expected` the loop is deterministic: it keeps polling until
        that many messages were handled (or timeout). Without it, it stops
        after 3 consecutive empty rounds.
        """
        deadline = time.monotonic() + timeout_s
        handled = 0
        # Wait for assignment; poll while waiting so nothing is missed.
        while time.monotonic() < deadline:
            try:
                if self.worker.consumer.assignment():
                    break
            except Exception:
                pass
            handled += self.worker.poll_once(num_messages=100, timeout_s=0.2)
        empty = 0
        rounds = 0
        while time.monotonic() < deadline and rounds < max_rounds:
            if expected is not None and handled >= expected:
                break
            n = self.worker.poll_once(num_messages=200, timeout_s=0.3)
            handled += n
            rounds += 1
            if expected is None:
                empty = 0 if n else empty + 1
                if empty >= 3:
                    break
        return handled

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.worker.stop()

    @property
    def paused_partitions(self):
        return self.worker.paused_partitions

    def committed(self, topic: str, partition: int) -> int:
        from confluent_kafka import TopicPartition

        parts = [TopicPartition(topic, partition)]
        res = self.worker.consumer.committed(parts, timeout=5)
        if not res or res[0].offset is None or res[0].offset < 0:
            return -1  # nothing committed (librdkafka uses -1001 OFFSET_INVALID)
        return res[0].offset


@pytest.fixture
def worker_factory(db, indexer):
    """Create WorkerHarness instances (caller supplies topics + group)."""
    from app.ingest.processor import EventProcessor
    from tests.fake_github import FakeGitHub, make_github_client

    made: list[WorkerHarness] = []

    def make(
        *,
        topics: list[str],
        group_id: str | None = None,
        fake: FakeGitHub | None = None,
        processor=None,
        indexer_override=None,
    ) -> WorkerHarness:
        if processor is None:
            if fake is None:
                fake = FakeGitHub()
            client, _ = make_github_client(fake)
            processor = EventProcessor(db, indexer_override or indexer, client)
        harness = WorkerHarness(
            processor, topics, group_id or f"kyro-test-group-{uuid.uuid4().hex[:10]}"
        )
        made.append(harness)
        return harness

    yield make
    for h in made:
        h.stop()


# ------------------------------------------------------------- messaging
def produce(
    bootstrap: str, topic: str, key: str, payload: dict, *, partition: int | None = None
) -> None:
    import json

    from confluent_kafka import Producer

    p = Producer(
        {
            "bootstrap.servers": bootstrap,
            "acks": "all",
            "enable.idempotence": True,
        }
    )
    kwargs: dict = {"partition": partition} if partition is not None else {}
    p.produce(
        topic,
        key=key.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
        **kwargs,
    )
    p.flush(10)


def probe_partition(bootstrap: str, topic: str, key: str) -> int:
    """Return the partition a key hashes to (via a probe message)."""
    import json
    import uuid as _uuid

    from confluent_kafka import Consumer, Producer

    probe_key = key
    p = Producer({"bootstrap.servers": bootstrap, "acks": "all"})
    token = _uuid.uuid4().hex
    p.produce(
        topic, key=probe_key.encode(), value=json.dumps({"probe": token}).encode()
    )
    p.flush(10)
    c = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": f"probe-{_uuid.uuid4().hex[:8]}",
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    c.subscribe([topic])
    msgs = c.consume(num_messages=1, timeout=5)
    c.close()
    if not msgs:
        raise RuntimeError("probe message not observed")
    part = msgs[0].partition()
    if part is None:
        raise RuntimeError("probe message missing partition")
    return part


# ---------------------------------------------------------- event helpers
def live_event(
    *,
    delivery_id: str,
    github_id: int = 1395956448,
    owner: str = "acme",
    name: str = "kyro-demo",
    installation_id: int | None = 791001,
    before: str | None = None,
    after: str | None = None,
    commits: list[dict] | None = None,
    changes: list[dict] | None = None,
    branch: str = "main",
    default_branch: str | None = "main",
) -> dict:
    """Build a live event matching the n8n workflow contract exactly."""
    return {
        "event": {
            "id": delivery_id,
            "type": "push",
            "received_at": "2025-01-01T00:00:00Z",
        },
        "installation": {"github_installation_id": installation_id},
        "repository": {
            "github_id": github_id,
            "name": name,
            "full_name": f"{owner}/{name}",
            "owner": owner,
            "private": False,
            "default_branch": default_branch,
            "url": f"https://github.com/{owner}/{name}",
        },
        "actor": {
            "github_id": 4242,
            "username": "alice",
            "name": "alice",
            "email": "alice@example.com",
        },
        "push": {
            "ref": f"refs/heads/{branch}",
            "branch": branch,
            "before": before,
            "after": after,
            "forced": False,
            "created": before is None,
            "deleted": False,
        },
        "commits": commits or [],
        "changes": changes or [],
    }


def live_event_for_head(fake, *, delivery_id: str, github_id: int = 1395956448) -> dict:
    """Build a n8n-contract live event for the fake repo's HEAD commit.

    Uses the real fake-GitHub detail (blob SHAs, patches, timestamps) so
    content resolution behaves exactly as against GitHub.
    """
    commit = fake.commits[-1]
    before = commit.parents[0] if commit.parents else None
    changes: list[dict] = []
    added: list[str] = []
    modified: list[str] = []
    removed: list[str] = []
    for e in commit.files:
        changes.append(
            {
                "path": e["filename"],
                "status": e["status"],
                "additions": e["additions"],
                "deletions": e["deletions"],
                "changes": e["changes"],
                "sha": e["sha"],
                "patch": e["patch"],
            }
        )
        if e["status"] == "added":
            added.append(e["filename"])
        elif e["status"] == "removed":
            removed.append(e["filename"])
        else:
            modified.append(e["filename"])
    return live_event(
        delivery_id=delivery_id,
        github_id=github_id,
        owner=fake.owner,
        name=fake.name,
        installation_id=fake.installation_id,
        before=before,
        after=commit.sha,
        branch=fake.default_branch or "main",
        default_branch=fake.default_branch,
        commits=[
            {
                "sha": commit.sha,
                "message": commit.message,
                "timestamp": commit.timestamp,
                "author": {
                    "name": commit.author_name,
                    "email": commit.author_email,
                    "username": None,
                },
                "committer": {
                    "name": commit.author_name,
                    "email": commit.author_email,
                    "username": None,
                },
                "added": added,
                "modified": modified,
                "removed": removed,
            }
        ],
        changes=changes,
    )


def sync_manager_for(
    session_factory,
    fake: FakeGitHub,
    *,
    backfill_topic: str,
    processor=None,
    timeout: float = 60.0,
    poll_interval: float = 0.05,
    indexer_override=None,
) -> SimpleNamespace:
    """Build a SyncManager wired to the fake GitHub and test topics."""
    from app.github.backfill import BackfillService
    from app.ingest.processor import EventProcessor
    from app.sync.manager import SyncManager
    from tests.fake_github import make_github_client

    client, _ = make_github_client(fake)
    idx = indexer_override
    if processor is None:
        if idx is None:
            from app.ingest.indexer import ChromaIndexer

            idx = ChromaIndexer(
                url=CHROMA_URL, collection_name=f"kyro_test_{uuid.uuid4().hex[:12]}"
            )
        processor = EventProcessor(session_factory, idx, client)
    manager = SyncManager(
        session_factory,
        BackfillService(client),
        processor,
        client,
        backfill_topic=backfill_topic,
        timeout=timeout,
        poll_interval=poll_interval,
        publish_batch=5,
        concurrency=2,
    )
    return SimpleNamespace(
        manager=manager,
        processor=processor,
        indexer=idx,
        client=client,
        fake=fake,
    )


@pytest.fixture
def processor_env(db, indexer):
    """EventProcessor wired to a fresh FakeGitHub + real Chroma collection."""
    from app.ingest.processor import EventProcessor
    from tests.fake_github import FakeGitHub, make_github_client

    fake = FakeGitHub()
    client, _ = make_github_client(fake)
    processor = EventProcessor(db, indexer, client)
    return SimpleNamespace(
        processor=processor, fake=fake, client=client, indexer=indexer, db=db
    )


def build_backfill_events(
    fake,
    *,
    stop_sha: str | None = None,
    target: str | None = None,
    branch: str | None = None,
) -> list[dict]:
    """Generate backfill events for the fake repo via the REAL BackfillService."""
    from app.github.backfill import BackfillService
    from tests.fake_github import make_github_client

    client, _ = make_github_client(fake)
    service = BackfillService(client, detail_concurrency=2)
    repo_block = {
        "github_id": 1395956448,
        "name": fake.name,
        "full_name": f"{fake.owner}/{fake.name}",
        "owner": fake.owner,
        "private": fake.private,
        "default_branch": fake.default_branch,
        "url": f"https://github.com/{fake.owner}/{fake.name}",
    }
    return [
        event
        for _, event in service.build_events(
            fake.owner,
            fake.name,
            repository=repo_block,
            branch=branch or fake.default_branch or "main",
            installation_id=fake.installation_id,
            stop_sha=stop_sha,
            target_sha=target or fake.head,
        )
    ]


def apply_event(processor, payload: dict, *, offset: int = 0, topic: str = "test"):
    """Run one payload through the full processor pipeline."""
    import json

    return processor.handle_raw(
        json.dumps(payload).encode("utf-8"),
        topic=topic,
        partition=0,
        offset=offset,
    )


def wait_for(predicate, *, timeout: float = 20.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def repo_row(session_factory, github_id: int):
    from sqlalchemy import select

    from app.db.models import Repository

    with session_factory() as session:
        return session.scalar(
            select(Repository).where(Repository.github_repository_id == github_id)
        )


def event_row(session_factory, event_id: str):
    from sqlalchemy import select

    from app.db.models import IngestionEvent

    with session_factory() as session:
        return session.scalar(
            select(IngestionEvent).where(IngestionEvent.event_id == event_id)
        )
