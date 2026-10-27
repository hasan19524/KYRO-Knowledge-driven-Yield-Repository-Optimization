"use client";

// Functional repository list (main KYRO: fetch /backend/api/repositories,
// selection, status, 5s polling) re-skinned with Lubna's design tokens.
// The "+ Connect" button opens the GitHub repo picker (Sign in with
// GitHub flow) inline below this list.

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Folder, Plus } from "lucide-react";
import { isSessionExpired } from "@/lib/auth";
import GithubRepoPicker from "./GithubRepoPicker";

export interface RepositorySummary {
  github_repository_id: number;
  full_name: string;
  status: string;
  deferred_events?: number;
  // Timing/status detail the backend snapshot already returns — surfaced for
  // the indexing wait screen (live elapsed clock, auto-dismiss on READY).
  sync_started_at?: string | null;
  sync_completed_at?: string | null;
  sync_running?: boolean;
  last_error?: string | null;
}

interface RepositorySectionProps {
  selectedId: number | null;
  onSelect: (repo: RepositorySummary) => void;
  /** Reports each successful poll so AppShell can keep its selected snapshot fresh. */
  onRepositoriesLoaded?: (repos: RepositorySummary[]) => void;
}

const STATUS_COLORS: Record<string, string> = {
  READY: "var(--kyro-success)",
  SYNCING: "var(--kyro-warning)",
  SYNC_FAILED: "var(--kyro-error)",
  ACCESS_REVOKED: "var(--kyro-error)",
};

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "var(--kyro-text-muted)";
}

export default function RepositorySection({
  selectedId,
  onSelect,
  onRepositoriesLoaded,
}: RepositorySectionProps) {
  const router = useRouter();
  const [repos, setRepos] = useState<RepositorySummary[] | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/backend/api/repositories", {
        cache: "no-store",
      });
      if (isSessionExpired(res)) {
        // A real 401 means the session is gone — route through login.
        // (5xx and network failures fall through to the offline state below;
        // they are NOT authentication failures.)
        router.replace("/login");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: unknown = await res.json();
      const parsed = Array.isArray(data) ? (data as RepositorySummary[]) : [];
      setRepos(parsed);
      setUnreachable(false);
      // Lift each fresh poll so AppShell's selected-repo snapshot tracks
      // SYNCING -> READY (this is what auto-dismisses the indexing panel).
      onRepositoriesLoaded?.(parsed);
    } catch {
      setUnreachable(true);
    }
  }, [router, onRepositoriesLoaded]);

  useEffect(() => {
    // load() only setStates after its fetch resolves (never synchronously);
    // the rule cannot see through the async boundary.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div
      className="mx-3 mb-3 rounded-[10px] px-3 py-3"
      style={{
        background: "var(--kyro-card)",
        border: "1px solid var(--kyro-border)",
      }}
    >
      <div className="mb-2.5 flex items-center justify-between">
        <span
          className="kyro-overline"
          style={{ color: "var(--kyro-accent-hover)" }}
        >
          Repositories
        </span>
        <div className="flex items-center gap-2">
          {unreachable && (
            <span className="text-[10px]" style={{ color: "var(--kyro-error)" }}>
              backend offline
            </span>
          )}
          <button
            type="button"
            onClick={() => setPickerOpen((open) => !open)}
            className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium transition-opacity hover:opacity-80"
            style={{ color: "var(--kyro-accent-hover)" }}
            aria-expanded={pickerOpen}
          >
            <Plus className="h-3 w-3" aria-hidden="true" />
            Connect
          </button>
        </div>
      </div>

      {repos === null && !unreachable && (
        <div className="text-[12px]" style={{ color: "var(--kyro-text-muted)" }}>
          Loading...
        </div>
      )}

      {repos !== null && repos.length === 0 && !unreachable && (
        <div className="text-[12px]" style={{ color: "var(--kyro-text-muted)" }}>
          No repositories yet
        </div>
      )}

      {repos !== null && repos.length === 0 && unreachable && (
        <div className="text-[12px]" style={{ color: "var(--kyro-error)" }}>
          Backend unreachable
        </div>
      )}

      <div className="flex flex-col gap-1">
        {repos?.map((repo) => {
          const selected = repo.github_repository_id === selectedId;
          return (
            <button
              key={repo.github_repository_id}
              type="button"
              onClick={() => onSelect(repo)}
              className="flex w-full items-center gap-2.5 rounded-md px-1.5 py-1.5 text-left transition-colors"
              style={{
                background: selected ? "var(--kyro-card-active)" : "transparent",
                border: selected
                  ? "1px solid var(--kyro-border-hover)"
                  : "1px solid transparent",
              }}
              title={repo.full_name}
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
                  className="truncate text-[13px] font-medium"
                  style={{ color: "var(--kyro-text)" }}
                >
                  {repo.full_name}
                </div>
                <div className="text-[11px]" style={{ color: "var(--kyro-text-muted)" }}>
                  {repo.status === "SYNCING" && "Synchronizing..."}
                  {repo.status === "READY" && "Ready"}
                  {repo.status === "SYNC_FAILED" && "Sync failed — resync required"}
                  {repo.status === "ACCESS_REVOKED" && "Access revoked"}
                  {repo.deferred_events
                    ? ` · ${repo.deferred_events} deferred`
                    : ""}
                </div>
              </div>
              <div
                className="h-2 w-2 flex-shrink-0 rounded-full"
                style={{ background: statusColor(repo.status) }}
              />
            </button>
          );
        })}
      </div>

      {pickerOpen && (
        <GithubRepoPicker
          onClose={() => setPickerOpen(false)}
          onConnected={load}
        />
      )}
    </div>
  );
}
