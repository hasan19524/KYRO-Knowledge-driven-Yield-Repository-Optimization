"use client";

import { useState, useCallback, useRef } from "react";
import { RefreshCw } from "lucide-react";
import WelcomeScreen from "./WelcomeScreen";
import MessageList from "./MessageList";
import ChatComposer from "./ChatComposer";
import RepositoryStatusPanel from "./RepositoryStatusPanel";
import { Chat } from "@/lib/storage";
import { RepositorySummary } from "./RepositorySection";
import { composerPlaceholder, isRepositoryBlocked } from "@/lib/repoStatus";

interface MainChatProps {
  activeChat: Chat | null;
  onSendMessage: (content: string) => void;
  repositoryLabel: string | null;
  /** Live snapshot of the selected repo — its status drives the wait screen. */
  repository: RepositorySummary | null;
  onResync: () => void;
  resyncing: boolean;
  resyncError: string | null;
}

/** Inline lock banner shown above the composer inside an existing chat. */
function StatusBanner({
  repository,
  onResync,
  resyncing,
  resyncError,
}: {
  repository: RepositorySummary;
  onResync: () => void;
  resyncing: boolean;
  resyncError: string | null;
}) {
  const failed = repository.status === "SYNC_FAILED";
  const revoked = repository.status === "ACCESS_REVOKED";
  const alert = failed || revoked;

  return (
    <div
      className="flex items-center gap-2.5 px-4 py-2.5 text-[12.5px]"
      style={{
        background: "var(--kyro-card)",
        borderTop: "1px solid var(--kyro-border)",
        color: "var(--kyro-text-secondary)",
      }}
      role="status"
    >
      <span
        className={`h-2 w-2 flex-shrink-0 rounded-full ${alert ? "" : "animate-pulse"}`}
        style={{ background: alert ? "var(--kyro-error)" : "var(--kyro-warning)" }}
      />
      <span className="min-w-0 flex-1 truncate">
        {failed
          ? `Indexing didn't finish — questions are paused until ${repository.full_name} is re-synced.`
          : revoked
            ? `GitHub access revoked — re-authorize the KYRO app to resume questions on ${repository.full_name}.`
            : `KYRO is indexing ${repository.full_name} — questions resume automatically when it's ready.`}
        {resyncError && (
          <span style={{ color: "var(--kyro-error)" }}> {resyncError}</span>
        )}
      </span>
      {failed && (
        <button
          type="button"
          onClick={onResync}
          disabled={resyncing}
          className="flex flex-shrink-0 items-center gap-1.5 rounded-md px-3 py-1 text-[12.5px] transition-colors disabled:opacity-60"
          style={{
            border: "1px solid var(--kyro-border-hover)",
            color: "var(--kyro-text)",
            background: "transparent",
          }}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${resyncing ? "animate-spin" : ""}`} />
          {resyncing ? "Starting…" : "Re-sync"}
        </button>
      )}
    </div>
  );
}

export default function MainChat({
  activeChat,
  onSendMessage,
  repositoryLabel,
  repository,
  onResync,
  resyncing,
  resyncError,
}: MainChatProps) {
  const [isLoading, setIsLoading] = useState(false);
  // Synchronous re-entry guard: state updates are async, so a second submit
  // could otherwise slip in before `isLoading` flips to true.
  const inFlight = useRef(false);

  const handleSend = useCallback(async (content: string) => {
    if (inFlight.current) return; // a query is already in flight
    inFlight.current = true;
    setIsLoading(true);
    try {
      await onSendMessage(content);
    } finally {
      inFlight.current = false;
      setIsLoading(false);
    }
  }, [onSendMessage]);

  const hasMessages = activeChat && activeChat.messages.length > 0;
  const blocked = isRepositoryBlocked(repository?.status ?? null);

  // No chat content yet and the repo can't answer: the status panel IS the
  // screen (indexing wait / failure+re-sync / revoked) — composer hidden.
  if (!hasMessages && blocked && repository) {
    return (
      <div
        className="flex flex-1 flex-col overflow-hidden"
        style={{ background: "var(--kyro-bg)" }}
      >
        <RepositoryStatusPanel
          repository={repository}
          onResync={onResync}
          resyncing={resyncing}
          resyncError={resyncError}
        />
      </div>
    );
  }

  if (hasMessages) {
    return (
      <div
        className="flex flex-1 flex-col overflow-hidden"
        style={{ background: "var(--kyro-bg)" }}
      >
        <MessageList messages={activeChat.messages} isLoading={isLoading} />
        {blocked && repository && (
          <StatusBanner
            repository={repository}
            onResync={onResync}
            resyncing={resyncing}
            resyncError={resyncError}
          />
        )}
        <div className="flex justify-center px-4 pb-4 pt-2">
          <div className="w-full max-w-[900px]">
            <ChatComposer
              onSend={handleSend}
              repositoryLabel={repositoryLabel}
              busy={isLoading}
              disabled={blocked}
              disabledReason={composerPlaceholder(
                repository?.status ?? null,
                repositoryLabel
              )}
            />
          </div>
        </div>
      </div>
    );
  }

  return <WelcomeScreen onSendMessage={handleSend} repositoryLabel={repositoryLabel} />;
}
