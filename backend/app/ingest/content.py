"""Exact current file content resolution.

Strategy (in order), always verified against the Git blob SHA carried by the
event when one is available:

  1. If we already track the file AND the event has a patch -> apply the
     unified diff to the known content (zero GitHub API calls).
  2. If the file is new (status=added) and the event has a patch -> the patch
     contains the entire file.
  3. Otherwise -> fetch the exact blob from GitHub at the event's commit
     (contents API, installation token). This is NOT a Compare call; the
     content is not present in the event, so it must be fetched once.

Any mismatch with the expected blob SHA falls back to (3); a mismatch after
(3) raises ContentResolutionError so the event stays retryable rather than
persisting wrong data.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from app.github.client import GitHubClient, GitHubError, GitHubNotFound

log = logging.getLogger("kyro.content")


class ContentResolutionError(RuntimeError):
    """Raised when exact content cannot be verified (event stays retryable)."""


class PatchApplyError(RuntimeError):
    pass


def git_blob_sha(content: str) -> str:
    raw = content.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def apply_unified_patch(base: str, patch: str) -> str:
    """Best-effort unified diff application.

    Correctness is enforced by the caller's blob-SHA verification: a wrong
    result here never reaches the database because the sha check falls back to
    fetching the exact blob from GitHub.
    """
    base_lines = base.split("\n")
    patch_lines = patch.split("\n")
    # Trailing empty element from final newline in patch text.
    if patch_lines and patch_lines[-1] == "":
        patch_lines.pop()

    out: list[str] = []
    idx = 0  # cursor into base_lines
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("@@"):
            header = line.split()
            try:
                old_start = int(header[1].split(",")[0].lstrip("-"))
            except (IndexError, ValueError) as exc:
                raise PatchApplyError(f"bad hunk header: {line}") from exc
            target = max(0, old_start - 1)
            # Locate hunk position: prefer declared position, else scan.
            if _hunk_matches(base_lines, target, patch_lines, i):
                pos = target
            else:
                pos = _scan_for_hunk(base_lines, patch_lines, i)
                if pos is None:
                    raise PatchApplyError("hunk context not found in base content")
            # Copy untouched prefix.
            out.extend(base_lines[idx:pos])
            cursor = pos
            i += 1
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                pline = patch_lines[i]
                if pline.startswith("\\"):
                    i += 1
                    continue
                tag = pline[:1] if pline else " "
                text = pline[1:]
                if tag == " ":
                    if cursor >= len(base_lines) or base_lines[cursor] != text:
                        raise PatchApplyError("context line mismatch")
                    out.append(base_lines[cursor])
                    cursor += 1
                elif tag == "+":
                    out.append(text)
                elif tag == "-":
                    if cursor >= len(base_lines) or base_lines[cursor] != text:
                        raise PatchApplyError("deleted line mismatch")
                    cursor += 1
                else:
                    raise PatchApplyError(f"unexpected patch line: {pline!r}")
                i += 1
            idx = cursor
            continue
        i += 1

    out.extend(base_lines[idx:])
    result = "\n".join(out)
    if base.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    if not base.endswith("\n") and result.endswith("\n"):
        result = result[:-1]
    return result


def _hunk_matches(
    base_lines: list[str], pos: int, patch_lines: list[str], hunk_i: int
) -> bool:
    cursor = pos
    j = hunk_i + 1
    while j < len(patch_lines) and not patch_lines[j].startswith("@@"):
        pline = patch_lines[j]
        if pline.startswith("\\"):
            j += 1
            continue
        tag = pline[:1] if pline else " "
        if tag in (" ", "-"):
            if cursor >= len(base_lines) or base_lines[cursor] != pline[1:]:
                return False
            cursor += 1
        j += 1
    return True


def _scan_for_hunk(
    base_lines: list[str], patch_lines: list[str], hunk_i: int
) -> int | None:
    for pos in range(len(base_lines) + 1):
        if _hunk_matches(base_lines, pos, patch_lines, hunk_i):
            return pos
    return None


@dataclass
class ResolvedContent:
    content: str | None
    blob_sha: str | None
    source: str  # patch | fetch | none


class ContentResolver:
    def __init__(
        self, client: GitHubClient, owner: str, name: str, installation_id: int | None
    ):
        self.client = client
        self.owner = owner
        self.name = name
        self.installation_id = installation_id

    def resolve(
        self,
        *,
        path: str,
        status: str,
        patch: str | None,
        expected_blob_sha: str | None,
        ref: str,
        known_content: str | None,
    ) -> ResolvedContent:
        if status == "deleted":
            return ResolvedContent(None, expected_blob_sha, "none")

        # 1. patch on top of known content
        if known_content is not None and patch:
            try:
                candidate = apply_unified_patch(known_content, patch)
                if expected_blob_sha and git_blob_sha(candidate) != expected_blob_sha:
                    raise PatchApplyError("blob sha mismatch after patch apply")
                return ResolvedContent(
                    candidate, expected_blob_sha or git_blob_sha(candidate), "patch"
                )
            except PatchApplyError as exc:
                log.debug("patch_apply_fallback path=%s reason=%s", path, exc)

        # 2. brand-new file fully described by its patch
        if known_content is None and patch and status in ("added", "new"):
            candidate = _full_content_from_patch(patch)
            if candidate is not None:
                if expected_blob_sha and git_blob_sha(candidate) != expected_blob_sha:
                    raise PatchApplyError("blob sha mismatch for added file")
                return ResolvedContent(
                    candidate, expected_blob_sha or git_blob_sha(candidate), "patch"
                )

        # 3. exact fetch from GitHub at the event commit
        try:
            content, blob_sha = self.client.get_file_content(
                self.owner, self.name, path, ref, self.installation_id
            )
        except GitHubNotFound:
            # File vanished between event creation and processing (or binary
            # edge): keep no content rather than inventing one.
            log.warning("content_not_found path=%s ref=%s", path, ref[:12])
            return ResolvedContent(None, expected_blob_sha, "none")
        except GitHubError as exc:
            raise ContentResolutionError(str(exc)) from exc

        if expected_blob_sha and blob_sha and blob_sha != expected_blob_sha:
            raise ContentResolutionError(
                f"blob sha mismatch for fetched content path={path}"
            )
        return ResolvedContent(content, expected_blob_sha or blob_sha, "fetch")


def _full_content_from_patch(patch: str) -> str | None:
    lines = patch.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    out: list[str] = []
    saw_hunk = False
    for line in lines:
        if line.startswith("@@"):
            saw_hunk = True
            continue
        if not saw_hunk:
            continue
        if line.startswith("\\"):
            continue
        if line.startswith("+") or line.startswith(" "):
            out.append(line[1:])
        elif line.startswith("-"):
            continue
        else:
            continue
    if not out:
        return None
    return "\n".join(out)
