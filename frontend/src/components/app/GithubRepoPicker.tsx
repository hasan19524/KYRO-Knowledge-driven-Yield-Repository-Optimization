"use client";

// GitHub repo picker: lists the signed-in user's GitHub repos (via the
// backend's installation-token listing) and connects them into KYRO through
// the existing onboard endpoint (which starts indexing).

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Folder, Lock, Plus, RefreshCw, X } from "lucide-react";
import { logout } from "@/lib/auth";
import {
  connectRepository,
  fetchGithubRepos,
  GithubRepoOption,
  repoStatusLabel,
  sortRepoOptions,
} from "@/lib/githubRepos";

interface GithubRepoPickerProps {
  /** Closes the panel; also called after a successful connect. */
  onClose: () => void;
  /** Notified after a connect so the sidebar list refreshes immediately. */
  onConnected?: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  READY: "var(--kyro-success)",
  SYNCING: "var(--kyro-warning)",
  SYNC_FAILED: "var(--kyro-error)",
  ACCESS_REVOKED: "var(--kyro-error)",
};

export default function GithubRepoPicker({
  onClose,
  onConnected,
}: GithubRepoPickerProps) {
  const router = useRouter();
  const [repos, setRepos] = useState<GithubRepoOption[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectingId, setConnectingId] = useState<number | null>(null);
  const [connectError, setConnectError] = useState<number | null>(null);
  const loadedOnce = useRef(false);

  const load = useCallback(async () => {
    const result = await fetchGithubRepos();
    if (!result.ok && result.sessionExpired) {
      await logout();
      router.replace("/login");
      return;
    }
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setError(null);
    setRepos(sortRepoOptions(result.repos));
  }, [router]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    loadedOnce.current = true;
  }, [load]);

  async function handleConnect(repo: GithubRepoOption) {
    if (connectingId !== null) return;
    setConnectingId(repo.github_repository_id);
    setConnectError(null);
    const result = await connectRepository(repo);
    setConnectingId(null);
    if (!result.ok && result.sessionExpired) {
      await logout();
      router.replace("/login");
      return;
    }
    if (!result.ok) {
      setConnectError(repo.github_repository_id);
      setError(result.message);
      return;
    }
    // Connected: flip the row to its new state and refresh the sidebar list.
    setRepos((prev) =>
      prev
        ? prev.map((r) =>
            r.github_repository_id === repo.github_repository_id
              ? { ...r, onboarded: true, status: "SYNCING" }
              : r
          )
        : prev
    );
    onConnected?.();
  }

  return (
    <div
      className="mt-3 rounded-[10px]"
      style={{
        background: "var(--kyro-card)",
        border: "1px solid var(--kyro-border-hover)",
      }}
      role="dialog"
      aria-label="Connect GitHub repositories"
    >
      <div
        className="flex items-center justify-between px-3 pb-2 pt-3"
        style={{ borderBottom: "1px solid var(--kyro-border)" }}
      >
        <span
          className="kyro-overline"
          style={{ color: "var(--kyro-accent-hover)" }}
        >
          Connect repositories
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close repository picker"
          className="rounded p-0.5 transition-colors hover:opacity-80"
          style={{ color: "var(--kyro-text-muted)" }}
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>

      <div className="flex flex-col gap-1 px-3 py-3">
        {repos === null && !error && (
          <div className="text-[12px]" style={{ color: "var(--kyro-text-muted)" }}>
            Loading your GitHub repositories…
          </div>
        )}

        {error && (
          <div className="text-[12px]" style={{ color: "var(--kyro-error)" }}>
            {error}
          </div>
        )}

        {repos !== null && repos.length === 0 && !error && (
          <div className="text-[12px]" style={{ color: "var(--kyro-text-muted)" }}>
            No repositories found for this GitHub account.
          </div>
        )}

        {repos?.map((repo) => {
          const connecting =
            connectingId === repo.github_repository_id;
          const failed = connectError === repo.github_repository_id;
          return (
            <div
              key={repo.github_repository_id}
              className="flex items-center gap-2.5 rounded-md px-1.5 py-1.5"
              title={repo.url ?? repo.full_name}
            >
              <div
                className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md"
                style={{
                  background: "var(--kyro-card-hover)",
                  border: "1px solid var(--kyro-border)",
                }}
              >
                <Folder
                  className="h-3.5 w-3.5"
                  style={{ color: "var(--kyro-text-muted)" }}
                />
              </div>
              <div className="min-w-0 flex-1">
                <div
                  className="flex items-center gap-1.5 truncate text-[13px] font-medium"
                  style={{ color: "var(--kyro-text)" }}
                >
                  <span className="truncate">{repo.full_name}</span>
                  {repo.private && (
                    <Lock
                      className="h-3 w-3 flex-shrink-0"
                      style={{ color: "var(--kyro-text-muted)" }}
                      aria-label="Private repository"
                    />
                  )}
                </div>
                <div className="text-[11px]" style={{ color: "var(--kyro-text-muted)" }}>
                  {repo.onboarded
                    ? repoStatusLabel(repo.status)
                    : failed
                      ? "Connect failed — try again"
                      : "Not connected"}
                  {!repo.onboarded && repo.default_branch
                    ? ` · ${repo.default_branch}`
                    : ""}
                </div>
              </div>
              {repo.onboarded ? (
                <div
                  className="h-2 w-2 flex-shrink-0 rounded-full"
                  style={{
                    background:
                      STATUS_COLORS[repo.status ?? ""] ??
                      "var(--kyro-text-muted)",
                  }}
                />
              ) : (
                <button
                  type="button"
                  disabled={connecting}
                  onClick={() => handleConnect(repo)}
                  className="flex flex-shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
                  style={{
                    background: "var(--kyro-accent)",
                    color: "var(--kyro-text)",
                  }}
                >
                  {connecting ? (
                    <RefreshCw className="h-3 w-3 animate-spin" aria-hidden="true" />
                  ) : (
                    <Plus className="h-3 w-3" aria-hidden="true" />
                  )}
                  {connecting ? "Connecting" : "Connect"}
                </button>
              )}
            </div>
          );
        })}

        <button
          type="button"
          onClick={() => void load()}
          disabled={repos === null}
          className="mt-1 flex items-center justify-center gap-1.5 rounded-md py-1.5 text-[11px] transition-opacity disabled:opacity-50"
          style={{ color: "var(--kyro-text-muted)" }}
        >
          <RefreshCw className="h-3 w-3" aria-hidden="true" />
          Refresh list
        </button>
      </div>
    </div>
  );
}
