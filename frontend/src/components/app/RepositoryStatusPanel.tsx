"use client";

// Full-panel repository status view — replaces the welcome screen while the
// selected repository is not queryable:
//   SYNCING        -> indexing wait screen (live elapsed clock + honest estimate)
//   SYNC_FAILED    -> failure notice + working Re-sync action (endpoint+proxy
//                     were already wired; this is the first UI that calls them)
//   ACCESS_REVOKED -> re-authorize instructions
//
// Estimate copy is grounded in measured single-repo ingestion times from this
// machine's database (Postgres, 2026-10-14): 54 files -> 59s, 129 files ->
// 170s, 442 files/153k churn -> 501s. Concurrent backfills queue behind the
// worker (concurrency=2) and ran up to ~22 min wall clock as a batch.

import { useEffect, useState } from "react";
import { RefreshCw, TriangleAlert, Lock } from "lucide-react";
import KyroLogo from "./KyroLogo";
import { RepositorySummary } from "./RepositorySection";
import { formatElapsed, truncateError } from "@/lib/repoStatus";

interface RepositoryStatusPanelProps {
  repository: RepositorySummary;
  onResync: () => void;
  resyncing: boolean;
  resyncError: string | null;
}

/**
 * Seconds elapsed since sync_started_at, ticking every second. The clock is
 * seeded inside the effect so server-rendered HTML never disagrees with the
 * first client render (Date.now() differs between the two passes).
 */
function useElapsedSeconds(startedAt: string | null | undefined): number | null {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    if (!startedAt) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- seeding the clock on mount avoids an SSR/hydration time mismatch
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  if (!startedAt || now === null) return null;
  const start = Date.parse(startedAt);
  if (Number.isNaN(start)) return null;
  return Math.max(0, Math.floor((now - start) / 1000));
}

function SyncingView({ repository }: { repository: RepositorySummary }) {
  const elapsed = useElapsedSeconds(repository.sync_started_at);

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-5 pb-16">
      <div className="flex w-full max-w-[560px] flex-col items-center">
        <div className="mb-5 animate-fade-in will-animate">
          <KyroLogo size={64} />
        </div>

        <h1
          className="animate-fade-in will-animate delay-100 text-center text-[24px] font-semibold leading-tight"
          style={{ color: "var(--kyro-text)", letterSpacing: "-0.02em" }}
        >
          Indexing {repository.full_name}
        </h1>

        <p
          className="animate-fade-in will-animate delay-200 mt-3 max-w-[470px] text-center text-[14px] leading-[1.65]"
          style={{ color: "var(--kyro-text-secondary)" }}
        >
          KYRO is reading this repository and building its semantic index.
          Most repositories are ready in{" "}
          <span style={{ color: "var(--kyro-text)" }}>1–8 minutes</span>; large
          repositories with deep history can take up to ~20.
        </p>

        {/* Indeterminate slide — honest: no per-phase telemetry exists yet. */}
        <div
          className="mt-8 w-full overflow-hidden rounded-full"
          style={{ height: "6px", background: "var(--kyro-card-active)" }}
          role="progressbar"
          aria-label="Indexing in progress"
        >
          <div
            className="kyro-indeterminate h-full rounded-full"
            style={{ width: "30%", background: "var(--kyro-accent-hover)" }}
          />
        </div>

        <div
          className="mt-3 flex w-full items-center justify-between text-[12px]"
          style={{ color: "var(--kyro-text-muted)" }}
        >
          <span className="flex items-center gap-2">
            <span
              className="animate-pulse h-1.5 w-1.5 rounded-full"
              style={{ background: "var(--kyro-warning)" }}
            />
            Indexing in progress
          </span>
          <span>{elapsed !== null ? `Elapsed ${formatElapsed(elapsed)}` : " "}</span>
        </div>

        <p
          className="animate-fade-in will-animate delay-300 mt-8 max-w-[440px] text-center text-[12px] leading-[1.6]"
          style={{ color: "var(--kyro-text-subtle)" }}
        >
          This runs once when a repository is first connected — after that, new
          pushes update the index in the background. Questions unlock
          automatically the moment indexing finishes.
        </p>
      </div>
    </div>
  );
}

function SyncFailedView({
  repository,
  onResync,
  resyncing,
  resyncError,
}: RepositoryStatusPanelProps) {
  const errorDetail = truncateError(repository.last_error);

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-5 pb-16">
      <div className="flex w-full max-w-[520px] flex-col items-center">
        <div
          className="animate-fade-in will-animate mb-5 flex h-14 w-14 items-center justify-center rounded-full"
          style={{ background: "var(--kyro-card)", border: "1px solid var(--kyro-border)" }}
        >
          <TriangleAlert className="h-6 w-6" style={{ color: "var(--kyro-error)" }} />
        </div>

        <h1
          className="animate-fade-in will-animate delay-100 text-center text-[22px] font-semibold leading-tight"
          style={{ color: "var(--kyro-text)", letterSpacing: "-0.02em" }}
        >
          Indexing didn&apos;t finish
        </h1>

        <p
          className="mt-3 max-w-[460px] text-center text-[14px] leading-[1.65]"
          style={{ color: "var(--kyro-text-secondary)" }}
        >
          The knowledge index for{" "}
          <span style={{ color: "var(--kyro-text)" }}>{repository.full_name}</span>{" "}
          is incomplete, so questions stay paused until it is re-indexed.
        </p>

        {errorDetail && (
          <p
            className="mt-4 w-full break-words rounded-lg px-3 py-2 text-[12px] leading-[1.55]"
            style={{
              background: "var(--kyro-card)",
              border: "1px solid var(--kyro-border)",
              color: "var(--kyro-text-muted)",
            }}
          >
            {errorDetail}
          </p>
        )}

        <button
          type="button"
          onClick={onResync}
          disabled={resyncing}
          className="mt-6 flex items-center gap-2 rounded-lg px-5 py-2.5 text-[13.5px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60"
          style={{ background: "var(--kyro-accent)", color: "var(--kyro-text)" }}
        >
          <RefreshCw className={`h-4 w-4 ${resyncing ? "animate-spin" : ""}`} />
          {resyncing ? "Starting re-sync…" : "Re-sync repository"}
        </button>

        {resyncError && (
          <p className="mt-3 text-center text-[12.5px]" style={{ color: "var(--kyro-error)" }}>
            {resyncError}
          </p>
        )}

        <p className="mt-5 text-center text-[12px]" style={{ color: "var(--kyro-text-subtle)" }}>
          Re-syncing re-reads the whole repository — typically 1–8 minutes.
        </p>
      </div>
    </div>
  );
}

function AccessRevokedView({ repository }: { repository: RepositorySummary }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-5 pb-16">
      <div className="flex w-full max-w-[520px] flex-col items-center">
        <div
          className="animate-fade-in will-animate mb-5 flex h-14 w-14 items-center justify-center rounded-full"
          style={{ background: "var(--kyro-card)", border: "1px solid var(--kyro-border)" }}
        >
          <Lock className="h-6 w-6" style={{ color: "var(--kyro-error)" }} />
        </div>

        <h1
          className="animate-fade-in will-animate delay-100 text-center text-[22px] font-semibold leading-tight"
          style={{ color: "var(--kyro-text)", letterSpacing: "-0.02em" }}
        >
          GitHub access revoked
        </h1>

        <p
          className="mt-3 max-w-[460px] text-center text-[14px] leading-[1.65]"
          style={{ color: "var(--kyro-text-secondary)" }}
        >
          KYRO no longer has permission to read{" "}
          <span style={{ color: "var(--kyro-text)" }}>{repository.full_name}</span>.
          Re-authorize the KYRO GitHub App in your GitHub settings to restore
          indexing and questions.
        </p>
      </div>
    </div>
  );
}

export default function RepositoryStatusPanel(
  props: RepositoryStatusPanelProps
) {
  const { repository } = props;
  if (repository.status === "SYNC_FAILED") return <SyncFailedView {...props} />;
  if (repository.status === "ACCESS_REVOKED") {
    return <AccessRevokedView repository={repository} />;
  }
  return <SyncingView repository={repository} />;
}
