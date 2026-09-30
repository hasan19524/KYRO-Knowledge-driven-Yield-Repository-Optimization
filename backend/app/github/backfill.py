"""Historical backfill: enumerate full Git history and emit one delta event
per commit, chronologically (parents before children).

Locked rules honored here:
  * entire history (no last-N truncation)
  * GitHub App installation API access only (no cloning, no PATs)
  * bounded API usage: paginated lists, bounded detail prefetch, retries/backoff
  * first commit = initial snapshot (before = null, all files added)
  * deterministic event ids -> re-publication is idempotent downstream
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app import config
from app.github.client import GitHubClient
from app.schemas.events import CLASSIFICATION_BACKFILL

log = logging.getLogger("kyro.backfill")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            UTC
        )
    except ValueError:
        return None


@dataclass
class CommitMeta:
    sha: str
    parents: list[str] = field(default_factory=list)
    message: str | None = None
    timestamp: datetime | None = None
    author_name: str | None = None
    author_email: str | None = None
    committer_name: str | None = None
    committer_email: str | None = None


def _meta_from_api(item: dict[str, Any]) -> CommitMeta:
    commit = item.get("commit") or {}
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    return CommitMeta(
        sha=item.get("sha", ""),
        parents=[p.get("sha", "") for p in item.get("parents") or [] if p.get("sha")],
        message=commit.get("message"),
        timestamp=_parse_ts(author.get("date") or committer.get("date")),
        author_name=author.get("name"),
        author_email=author.get("email"),
        committer_name=committer.get("name"),
        committer_email=committer.get("email"),
    )


class BackfillService:
    def __init__(
        self, client: GitHubClient, detail_concurrency: int | None = None
    ) -> None:
        self.client = client
        self.detail_concurrency = (
            detail_concurrency
            if detail_concurrency is not None
            else config.GITHUB_DETAIL_CONCURRENCY
        )

    # ------------------------------------------------------------ enumeration
    def collect_history(
        self,
        owner: str,
        name: str,
        *,
        branch: str,
        installation_id: int | None,
        stop_sha: str | None = None,
    ) -> list[CommitMeta]:
        """Fetch the full reachable history (newest -> oldest), stopping early
        at `stop_sha` (the already-published boundary), then return it in
        chronological order (parents before children). The boundary commit
        itself is EXCLUDED (already published); its ancestors are older than
        the boundary and are never reached."""
        items: list[CommitMeta] = []
        stop_seen = stop_sha is None
        for item in self.client.iter_commits(
            owner, name, sha=branch, installation_id=installation_id, stop_sha=stop_sha
        ):
            if stop_sha is not None and item.get("sha") == stop_sha:
                stop_seen = True
                break
            items.append(_meta_from_api(item))
        if not stop_seen:
            # Boundary not found in this walk (history rewritten?): keep what
            # we saw; deterministic event ids make re-publication harmless.
            log.warning(
                "backfill_stop_sha_not_found owner=%s repo=%s stop_sha=%s",
                owner,
                name,
                (stop_sha or "")[:12],
            )
        return _chronological(items)

    # ----------------------------------------------------------- event build
    def build_event(
        self,
        meta: CommitMeta,
        detail: dict[str, Any],
        *,
        repository: dict[str, Any],
        installation_id: int | None,
        branch: str,
        sequence: int,
        total: int,
        target_sha: str | None,
    ) -> dict[str, Any]:
        files = detail.get("files") or []
        changes = [
            {
                "path": f.get("filename"),
                "status": f.get("status", "modified"),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "changes": f.get("changes", 0),
                "sha": f.get("sha"),
                "patch": f.get("patch"),
                "previous_path": f.get("previous_filename"),
            }
            for f in files
            if f.get("filename")
        ]

        added = [c["path"] for c in changes if c["status"] == "added"]
        removed = [c["path"] for c in changes if c["status"] == "removed"]
        modified = [
            c["path"]
            for c in changes
            if c["status"] in ("modified", "changed", "renamed", "copied")
        ]

        parent_sha = meta.parents[0] if meta.parents else None
        is_initial = parent_sha is None

        return {
            "event": {
                "id": f"backfill:{repository['github_id']}:{meta.sha}",
                "type": "push",
                "received_at": datetime.now(UTC).isoformat(),
                "classification": CLASSIFICATION_BACKFILL,
            },
            "installation": {"github_installation_id": installation_id},
            "repository": repository,
            "actor": {
                "github_id": None,
                "username": None,
                "name": meta.author_name,
                "email": meta.author_email,
            },
            "push": {
                "ref": f"refs/heads/{branch}",
                "branch": branch,
                "before": parent_sha,
                "after": meta.sha,
                "forced": False,
                "created": is_initial,
                "deleted": False,
            },
            "commits": [
                {
                    "sha": meta.sha,
                    "message": meta.message,
                    "timestamp": meta.timestamp.isoformat() if meta.timestamp else None,
                    "author": {
                        "name": meta.author_name,
                        "email": meta.author_email,
                        "username": None,
                    },
                    "committer": {
                        "name": meta.committer_name,
                        "email": meta.committer_email,
                        "username": None,
                    },
                    "added": added,
                    "modified": modified,
                    "removed": removed,
                }
            ],
            "changes": changes,
            "backfill": {
                "sequence": sequence,
                "is_initial_commit": is_initial,
                "parent_sha": parent_sha,
                "sync_target_commit": target_sha,
            },
        }

    def build_events(
        self,
        owner: str,
        name: str,
        *,
        repository: dict[str, Any],
        branch: str,
        installation_id: int | None,
        stop_sha: str | None = None,
        target_sha: str | None = None,
    ) -> Iterator[tuple[CommitMeta, dict[str, Any]]]:
        """Yield (meta, event) in chronological order for the unpublished range.

        Commit details are prefetched with bounded concurrency while emission
        stays strictly ordered.
        """
        history = self.collect_history(
            owner,
            name,
            branch=branch,
            installation_id=installation_id,
            stop_sha=stop_sha,
        )
        total = len(history)
        if total == 0:
            return

        inflight = max(1, self.detail_concurrency)

        def emit(
            sequence: int, meta: CommitMeta, future
        ) -> tuple[CommitMeta, dict[str, Any]]:
            detail = future.result()
            event = self.build_event(
                meta,
                detail,
                repository=repository,
                installation_id=installation_id,
                branch=branch,
                sequence=sequence,
                total=total,
                target_sha=target_sha,
            )
            return meta, event

        with ThreadPoolExecutor(max_workers=inflight) as pool:
            pending: deque = deque()
            for sequence, meta in enumerate(history):
                pending.append(
                    (
                        sequence,
                        meta,
                        pool.submit(
                            self.client.get_commit,
                            owner,
                            name,
                            meta.sha,
                            installation_id,
                        ),
                    )
                )
                while len(pending) > inflight:
                    seq, m, fut = pending.popleft()
                    yield emit(seq, m, fut)
            while pending:
                seq, m, fut = pending.popleft()
                yield emit(seq, m, fut)


def _chronological(items: list[CommitMeta]) -> list[CommitMeta]:
    """Order commits so parents always precede children (topological), using
    committer timestamp as the tie-breaker for stability.

    Only metadata is held in memory; file contents are never buffered here.
    """
    by_sha = {m.sha: m for m in items}
    indegree = {m.sha: 0 for m in items}
    children: dict[str, list[str]] = {m.sha: [] for m in items}
    for m in items:
        for parent in m.parents:
            if parent in by_sha:
                indegree[m.sha] += 1
                children[parent].append(m.sha)

    def sort_key(sha: str) -> tuple:
        ts = by_sha[sha].timestamp or datetime.min.replace(tzinfo=UTC)
        return (ts, sha)

    ready = sorted((sha for sha, deg in indegree.items() if deg == 0), key=sort_key)
    ordered: list[CommitMeta] = []
    while ready:
        sha = ready.pop(0)
        ordered.append(by_sha[sha])
        for child in children[sha]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort(key=sort_key)

    if len(ordered) != len(items):
        # Real Git DAGs are acyclic; defensive fallback keeps every commit
        # (timestamp order) rather than silently dropping any.
        seen = {m.sha for m in ordered}
        remainder = sorted(
            (m for m in items if m.sha not in seen), key=lambda m: sort_key(m.sha)
        )
        ordered.extend(remainder)
    return ordered
