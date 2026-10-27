"""Binary-file retrieval defect regression (multi-repo demo prep).

GitHub's compare API omits patches for binary files and the contents API
returns raw bytes that do not decode as UTF-8, so the resolver reports
(content=None, source="fetch"). The old code treated ANY content=None as
deletion, which

  * tombstoned live binary files (is_deleted=True although the file
    exists at the ref), and
  * still indexed a header-only chunk for them, whose generic document
    matched every query and crowded real text hits out of the retrieval
    window (image-heavy repos returned refs=0).

These tests pin the fixed behaviour: a successful fetch with no decodable
text keeps the file alive, stores no content, and produces no index item;
real deletions and text files keep their previous behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import CommitFile, File, Repository
from app.ingest.content import ResolvedContent
from app.ingest.persistence import apply_payload
from app.schemas.events import (
    ChangeBlock,
    CommitBlock,
    EventBlock,
    IngestionEventPayload,
    PushBlock,
    RepositoryBlock,
)

GITHUB_ID = 888_000_111
SHA = "a" * 40
BLOB_SHA = "b" * 40


class _StubResolver:
    """Resolver stub: returns canned ResolvedContent per path."""

    def __init__(self, by_path: dict[str, ResolvedContent]) -> None:
        self.by_path = by_path

    def resolve(self, *, path, status, patch, expected_blob_sha, ref, known_content):
        return self.by_path[path]


def _payload(*, status: str, patch: str | None, path: str) -> IngestionEventPayload:
    return IngestionEventPayload(
        event=EventBlock(id="delivery-1", classification="live"),
        repository=RepositoryBlock(
            github_id=GITHUB_ID,
            name="binary-repo",
            full_name="hasan19524/binary-repo",
            owner="hasan19524",
        ),
        push=PushBlock(
            ref="refs/heads/main",
            branch="main",
            before="0" * 40,
            after=SHA,
        ),
        commits=[
            CommitBlock(
                sha=SHA,
                message="Add asset",
                timestamp=datetime.now(UTC).isoformat(),
                added=[path] if status == "added" else [],
            )
        ],
        changes=[
            ChangeBlock(
                path=path,
                status=status,
                additions=1,
                deletions=0,
                changes=1,
                sha=BLOB_SHA,
                patch=patch,
            )
        ],
    )


def test_binary_file_stays_alive_and_is_not_indexed(db):
    payload = _payload(status="added", patch=None, path="public/images/logo.png")
    resolver = _StubResolver(
        {"public/images/logo.png": ResolvedContent(None, BLOB_SHA, "fetch")}
    )
    with db() as session:
        result = apply_payload(session, payload, resolver=resolver)
        session.commit()

        file_row = session.scalar(
            select(File).where(
                File.repository_id == result.repository.id,
                File.path == "public/images/logo.png",
            )
        )
        assert file_row is not None
        # A successful fetch that decodes to no text is NOT a deletion.
        assert file_row.is_deleted is False
        assert file_row.current_content is None
        assert file_row.blob_sha == BLOB_SHA
        # History is preserved (commit_files row exists, status added).
        cf = session.scalar(select(CommitFile).where(CommitFile.file_id == file_row.id))
        assert cf is not None
        assert cf.status == "added"

    # No junk header-only chunk for the binary file.
    assert result.index_items == []


def test_real_deletion_still_tombstones(db):
    payload = _payload(status="removed", patch=None, path="gone.txt")
    resolver = _StubResolver({"gone.txt": ResolvedContent(None, BLOB_SHA, "none")})
    with db() as session:
        result = apply_payload(session, payload, resolver=resolver)
        session.commit()
        file_row = session.scalar(
            select(File).where(
                File.repository_id == result.repository.id, File.path == "gone.txt"
            )
        )
        assert file_row is not None
        assert file_row.is_deleted is True


def test_text_file_still_indexed(db):
    patch = "@@ -0,0 +1 @@\n+hello"
    payload = _payload(status="added", patch=patch, path="README.md")
    resolver = _StubResolver({"README.md": ResolvedContent("hello", BLOB_SHA, "patch")})
    with db() as session:
        result = apply_payload(session, payload, resolver=resolver)
        session.commit()
        file_row = session.scalar(
            select(File).where(
                File.repository_id == result.repository.id, File.path == "README.md"
            )
        )
        assert file_row is not None
        assert file_row.is_deleted is False
        assert file_row.current_content == "hello"

    assert len(result.index_items) == 1
    assert result.index_items[0].path == "README.md"


def test_mixed_event_indexes_text_skips_binary(db):
    """One push with a text + a binary file: only the text file is indexed."""
    text_patch = "@@ -0,0 +1 @@\n+hello"
    payload = IngestionEventPayload(
        event=EventBlock(id="delivery-2", classification="live"),
        repository=RepositoryBlock(
            github_id=GITHUB_ID,
            name="binary-repo",
            full_name="hasan19524/binary-repo",
            owner="hasan19524",
        ),
        push=PushBlock(
            ref="refs/heads/main", branch="main", before="0" * 40, after=SHA
        ),
        commits=[
            CommitBlock(
                sha=SHA,
                message="Add files",
                timestamp=datetime.now(UTC).isoformat(),
                added=["app.py", "img.jpg"],
            )
        ],
        changes=[
            ChangeBlock(path="app.py", status="added", sha=BLOB_SHA, patch=text_patch),
            ChangeBlock(path="img.jpg", status="added", sha="c" * 40, patch=None),
        ],
    )
    resolver = _StubResolver(
        {
            "app.py": ResolvedContent("hello", BLOB_SHA, "patch"),
            "img.jpg": ResolvedContent(None, "c" * 40, "fetch"),
        }
    )
    with db() as session:
        result = apply_payload(session, payload, resolver=resolver)
        session.commit()
        repo = session.scalar(
            select(Repository).where(Repository.github_repository_id == GITHUB_ID)
        )
        img = session.scalar(
            select(File).where(File.repository_id == repo.id, File.path == "img.jpg")
        )
        assert img is not None and img.is_deleted is False

    indexed_paths = [i.path for i in result.index_items]
    assert indexed_paths == ["app.py"]
