/**
 * GitHub repo picker logic (Sign in with GitHub -> connect repositories).
 *
 * Pure helpers are kept free of React/Next imports so they can be unit-tested
 * with the Node test runner (`npm test`), matching the proxyPolicy.ts pattern.
 * The fetch wrappers go through the Next.js backend proxy like lib/auth.ts.
 */

/** One repo as returned by GET /backend/api/github/repos (backend RepoOption). */
export interface GithubRepoOption {
  github_repository_id: number;
  full_name: string;
  name: string;
  owner: string;
  private: boolean;
  default_branch: string | null;
  url: string | null;
  /** Already ingested by KYRO (any identity) — shows status, not a button. */
  onboarded: boolean;
  status: string | null;
}

export type RepoPickerResult =
  | { ok: true; repos: GithubRepoOption[] }
  | { ok: false; message: string; sessionExpired?: boolean };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown, fallback: string): string {
  return typeof value === "string" && value !== "" ? value : fallback;
}

function asOptionalString(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

/**
 * Validates the picker payload defensively — one malformed entry must not
 * crash the panel; bad entries are skipped, unreadable payloads fail closed.
 */
export function parseRepoOptions(data: unknown): GithubRepoOption[] | null {
  if (!Array.isArray(data)) return null;
  const repos: GithubRepoOption[] = [];
  for (const entry of data) {
    if (!isRecord(entry)) continue;
    const id = entry["github_repository_id"];
    if (typeof id !== "number" || !Number.isFinite(id)) continue;
    const fullName = asString(entry["full_name"], `repo-${id}`);
    repos.push({
      github_repository_id: id,
      full_name: fullName,
      name: asString(entry["name"], fullName),
      owner: asString(entry["owner"], fullName.split("/")[0] ?? fullName),
      private: entry["private"] === true,
      default_branch: asOptionalString(entry["default_branch"]),
      url: asOptionalString(entry["url"]),
      onboarded: entry["onboarded"] === true,
      status: asOptionalString(entry["status"]),
    });
  }
  return repos;
}

/**
 * Connected repos first (they need no action), then available ones; each
 * group alphabetical so the list is stable between polls.
 */
export function sortRepoOptions(repos: GithubRepoOption[]): GithubRepoOption[] {
  return [...repos].sort((a, b) => {
    if (a.onboarded !== b.onboarded) return a.onboarded ? -1 : 1;
    return a.full_name.localeCompare(b.full_name);
  });
}

/** Body for POST /backend/api/repositories/onboard (all fields GitHub gave us). */
export function connectPayload(repo: GithubRepoOption): Record<string, unknown> {
  return {
    github_repository_id: repo.github_repository_id,
    owner: repo.owner,
    name: repo.name,
    full_name: repo.full_name,
    default_branch: repo.default_branch ?? undefined,
    private: repo.private,
    url: repo.url ?? undefined,
  };
}

/** Human label for a KYRO sync status shown in the picker. */
export function repoStatusLabel(status: string | null): string {
  switch (status) {
    case "READY":
      return "Connected";
    case "SYNCING":
      return "Indexing…";
    case "SYNC_FAILED":
      return "Sync failed";
    case "ACCESS_REVOKED":
      return "Access revoked";
    default:
      return status ? status : "Connected";
  }
}

function messageFromDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first: unknown = detail[0];
    if (isRecord(first) && "msg" in first) return String(first["msg"]);
    return null;
  }
  if (isRecord(detail) && typeof detail["message"] === "string") {
    return detail["message"];
  }
  return null;
}

/** Loads the GitHub repo list (session cookie handled by the proxy). */
export async function fetchGithubRepos(): Promise<RepoPickerResult> {
  let res: Response;
  try {
    res = await fetch("/backend/api/github/repos", { cache: "no-store" });
  } catch {
    return { ok: false, message: "KYRO backend is unreachable. Is it running?" };
  }
  if (res.status === 401) {
    return { ok: false, message: "Your session has expired.", sessionExpired: true };
  }
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    return {
      ok: false,
      message: messageFromDetail(detail) ?? `Could not load repositories (HTTP ${res.status})`,
    };
  }
  const repos = parseRepoOptions(data);
  if (repos === null) {
    return { ok: false, message: "KYRO returned an unreadable repository list." };
  }
  return { ok: true, repos };
}

export type ConnectResult =
  | { ok: true }
  | { ok: false; message: string; sessionExpired?: boolean };

/** Connects one repo through the existing onboard endpoint (starts indexing). */
export async function connectRepository(
  repo: GithubRepoOption
): Promise<ConnectResult> {
  let res: Response;
  try {
    res = await fetch("/backend/api/repositories/onboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(connectPayload(repo)),
    });
  } catch {
    return { ok: false, message: "KYRO backend is unreachable. Is it running?" };
  }
  if (res.status === 401) {
    return { ok: false, message: "Your session has expired.", sessionExpired: true };
  }
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    return {
      ok: false,
      message: messageFromDetail(detail) ?? `Connect failed (HTTP ${res.status})`,
    };
  }
  return { ok: true };
}
