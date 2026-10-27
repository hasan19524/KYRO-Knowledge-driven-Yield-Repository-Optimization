/**
 * Pure repository-status helpers for the indexing wait screen.
 *
 * Kept free of React/Next imports so they can be unit-tested with the Node
 * test runner (`npm test`), matching the proxyPolicy.ts pattern.
 */

/** Statuses that must block queries (mirrors backend §13 / §76 query gating). */
export const BLOCKED_REPOSITORY_STATUSES = new Set([
  "SYNCING",
  "SYNC_FAILED",
  "ACCESS_REVOKED",
]);

export function isRepositoryBlocked(
  status: string | null | undefined
): boolean {
  return typeof status === "string" && BLOCKED_REPOSITORY_STATUSES.has(status);
}

/** "1:05"-style elapsed clock; floors at 0 for clock skew, drops fractions. */
export function formatElapsed(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** Placeholder shown while the composer is locked — tells the user why. */
export function composerPlaceholder(
  status: string | null | undefined,
  repositoryLabel: string | null
): string {
  const name = repositoryLabel ?? "this repository";
  if (status === "SYNC_FAILED") {
    return "Indexing didn't finish — re-sync required";
  }
  if (status === "ACCESS_REVOKED") {
    return "GitHub access revoked — re-authorize the KYRO app";
  }
  return `KYRO is indexing ${name} — questions resume when it's ready`;
}

/** Trim backend error detail for display (collapse whitespace, bound length). */
export function truncateError(
  message: string | null | undefined,
  maxLength = 200
): string {
  if (!message) return "";
  const singleLine = message.replace(/\s+/g, " ").trim();
  if (singleLine.length <= maxLength) return singleLine;
  return `${singleLine.slice(0, maxLength - 1)}…`;
}
