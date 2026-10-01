"use client";

import { useCallback, useEffect, useState } from "react";
import { Folder } from "lucide-react";

export interface RepositorySummary {
  github_repository_id: number;
  full_name: string;
  status: string;
  deferred_events?: number;
}

interface RepositorySectionProps {
  selectedId: number | null;
  onSelect: (repo: RepositorySummary) => void;
}

const STATUS_COLORS: Record<string, string> = {
  READY: "#22c55e",
  SYNCING: "#f59e0b",
  SYNC_FAILED: "#ef4444",
  ACCESS_REVOKED: "#ef4444",
};

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "#626977";
}

export default function RepositorySection({
  selectedId,
  onSelect,
}: RepositorySectionProps) {
  const [repos, setRepos] = useState<RepositorySummary[] | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/backend/api/repositories", {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: unknown = await res.json();
      setRepos(Array.isArray(data) ? (data as RepositorySummary[]) : []);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

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
      className="mx-3 mb-2 rounded-lg px-3 py-3"
      style={{
        background: "#12151c",
        border: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <div className="mb-2.5 flex items-center justify-between">
        <span
          className="text-[11px] font-medium"
          style={{ color: "#626977" }}
        >
          Repositories
        </span>
        {unreachable && (
          <span className="text-[10px]" style={{ color: "#ef4444" }}>
            backend offline
          </span>
        )}
      </div>

      {repos === null && !unreachable && (
        <div className="text-[12px]" style={{ color: "#626977" }}>
          Loading...
        </div>
      )}

      {repos !== null && repos.length === 0 && !unreachable && (
        <div className="text-[12px]" style={{ color: "#626977" }}>
          No repositories yet
        </div>
      )}

      {repos !== null && repos.length === 0 && unreachable && (
        <div className="text-[12px]" style={{ color: "#8f96a3" }}>
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
                background: selected ? "#1a1e27" : "transparent",
                border: selected
                  ? "1px solid rgba(255,255,255,0.10)"
                  : "1px solid transparent",
              }}
              title={repo.full_name}
            >
              <div
                className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md"
                style={{
                  background: "#1a1e27",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
              >
                <Folder className="h-3.5 w-3.5" style={{ color: "#8f96a3" }} />
              </div>
              <div className="min-w-0 flex-1">
                <div
                  className="truncate text-[13px] font-medium"
                  style={{ color: "#f5f5f5" }}
                >
                  {repo.full_name}
                </div>
                <div className="text-[11px]" style={{ color: "#626977" }}>
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
    </div>
  );
}
