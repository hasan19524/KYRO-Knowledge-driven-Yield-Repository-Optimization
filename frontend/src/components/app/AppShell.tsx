"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "./Sidebar";
import MainChat from "./MainChat";
import Topbar from "./Topbar";
import { Chat, getAllChats, saveChat, createChat, addMessageToChat, deleteChat } from "@/lib/storage";
import { RepositorySummary } from "./RepositorySection";
import { AuthUser, isSessionExpired, logout } from "@/lib/auth";

interface QueryReference {
  commit_sha: string | null;
  path: string | null;
  additions: number;
  deletions: number;
}

interface QueryAnswer {
  answer: string;
  references: QueryReference[];
}

/** Thrown when a protected request returns a real 401 (session expired). */
class SessionExpiredError extends Error {
  constructor() {
    super("Your session has expired. Please sign in again.");
    this.name = "SessionExpiredError";
  }
}

function formatReferences(refs: QueryReference[] | undefined): string {
  if (!refs || refs.length === 0) return "";
  const lines = refs.slice(0, 5).map((r) => {
    const sha = (r.commit_sha ?? "").slice(0, 7) || "???????";
    return `${sha} ${r.path ?? "?"} (+${r.additions}/-${r.deletions})`;
  });
  return `\n\nReferences:\n${lines.join("\n")}`;
}

async function askRepository(
  repositoryId: number,
  question: string
): Promise<QueryAnswer> {
  const res = await fetch("/backend/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      github_repository_id: repositoryId,
      question,
    }),
  });

  const data: unknown = await res.json().catch(() => null);
  if (res.status === 401) {
    // Session expired mid-session — distinct from 5xx/backend failures.
    throw new SessionExpiredError();
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") throw new Error(message);
    }
    throw new Error(`Query failed (HTTP ${res.status})`);
  }
  return data as QueryAnswer;
}

export default function AppShell({ user }: { user: AuthUser | null }) {
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [selectedRepo, setSelectedRepo] = useState<RepositorySummary | null>(null);
  const [isMobile, setIsMobile] = useState(false);
  const [resyncing, setResyncing] = useState(false);
  // Keyed to its repo so a leftover error never shows for a different repo.
  const [resyncError, setResyncError] = useState<{
    repoId: number;
    message: string;
  } | null>(null);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  useEffect(() => {
    // localStorage is browser-only; hydrate after mount so the first client
    // render matches the server-rendered empty state (no hydration mismatch).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setChats(getAllChats());
  }, []);

  const activeChat = activeChatId ? chats.find((c) => c.id === activeChatId) || null : null;

  const handleNewChat = useCallback(() => {
    setActiveChatId(null);
    if (isMobile) setSidebarOpen(false);
  }, [isMobile]);

  const handleSelectChat = useCallback((id: string) => {
    setActiveChatId(id);
    if (isMobile) setSidebarOpen(false);
  }, [isMobile]);

  const handleSendMessage = useCallback(async (content: string) => {
    let chatId = activeChatId;
    let currentChat = chatId ? chats.find((c) => c.id === chatId) || null : null;

    if (!currentChat) {
      const newChat = createChat(content);
      currentChat = { ...newChat, messages: [] };
      saveChat(currentChat);
      chatId = currentChat.id;
      setActiveChatId(chatId);
      setChats(getAllChats());
    }

    const userMsg = { role: "user" as const, content, timestamp: Date.now() };
    addMessageToChat(currentChat!.id, userMsg);
    setChats(getAllChats());

    const appendAssistant = (text: string) => {
      const assistantMsg = { role: "assistant" as const, content: text, timestamp: Date.now() };
      addMessageToChat(currentChat!.id, assistantMsg);
      setChats(getAllChats());
    };

    if (!selectedRepo) {
      appendAssistant(
        "No repository selected. Choose a repository in the sidebar first."
      );
      return;
    }

    try {
      const data = await askRepository(selectedRepo.github_repository_id, content);
      appendAssistant(data.answer + formatReferences(data.references));
    } catch (err) {
      if (err instanceof SessionExpiredError) {
        // Clear invalid client-visible state and route through login.
        await logout();
        router.replace("/login");
        return;
      }
      const errorMsg = err instanceof Error ? err.message : "An error occurred";
      appendAssistant(`Error: ${errorMsg}`);
    }
  }, [activeChatId, chats, selectedRepo, router]);

  const handleDeleteChat = useCallback((id: string) => {
    deleteChat(id);
    setChats(getAllChats());
    if (activeChatId === id) setActiveChatId(null);
  }, [activeChatId]);

  const handleRepositoriesLoaded = useCallback((repos: RepositorySummary[]) => {
    // The sidebar polls every 5s; keep the selected snapshot in lockstep so
    // the indexing panel auto-dismisses when the repo flips to READY.
    setSelectedRepo((prev) => {
      if (!prev) return prev;
      const fresh = repos.find(
        (r) => r.github_repository_id === prev.github_repository_id
      );
      if (!fresh) return prev;
      const unchanged =
        fresh.status === prev.status &&
        fresh.full_name === prev.full_name &&
        fresh.sync_started_at === prev.sync_started_at &&
        fresh.sync_running === prev.sync_running &&
        fresh.last_error === prev.last_error &&
        fresh.deferred_events === prev.deferred_events;
      return unchanged ? prev : fresh;
    });
  }, []);

  const handleResync = useCallback(async () => {
    const repo = selectedRepo;
    if (!repo || resyncing) return;
    setResyncing(true);
    setResyncError(null);
    try {
      const res = await fetch(
        `/backend/api/repositories/${repo.github_repository_id}/resync`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ full: false }),
        }
      );
      if (isSessionExpired(res)) {
        await logout();
        router.replace("/login");
        return;
      }
      const data: unknown = await res.json().catch(() => null);
      if (!res.ok) {
        const detail = (data as { detail?: unknown } | null)?.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : `Re-sync failed (HTTP ${res.status})`
        );
      }
      // The 202 response is the fresh snapshot — flip the panel immediately;
      // the sidebar's 5s poll keeps it correct from there.
      if (data && typeof data === "object" && "status" in data) {
        const snap = data as Partial<RepositorySummary>;
        setSelectedRepo((prev) =>
          prev
            ? {
                ...prev,
                ...snap,
                github_repository_id: prev.github_repository_id,
              }
            : prev
        );
      }
    } catch (err) {
      setResyncError({
        repoId: repo.github_repository_id,
        message: err instanceof Error ? err.message : "Re-sync request failed",
      });
    } finally {
      setResyncing(false);
    }
  }, [selectedRepo, resyncing, router]);

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace("/login");
  }, [router]);

  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ background: "var(--kyro-bg)" }}>
      {isMobile && sidebarOpen && (
        <div
          className="fixed inset-0 z-40"
          style={{ background: "var(--kyro-overlay)" }}
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <div
        className={`flex-shrink-0 transition-all duration-300 ease-in-out ${
          isMobile
            ? `fixed inset-y-0 left-0 z-50 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`
            : ""
        }`}
        style={{
          width: sidebarCollapsed && !isMobile ? "64px" : "264px",
        }}
      >
        <Sidebar
          chats={chats}
          activeChatId={activeChatId}
          collapsed={sidebarCollapsed && !isMobile}
          selectedRepositoryId={selectedRepo?.github_repository_id ?? null}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          onNewChat={handleNewChat}
          onSelectChat={handleSelectChat}
          onDeleteChat={handleDeleteChat}
          onSelectRepository={setSelectedRepo}
          onRepositoriesLoaded={handleRepositoriesLoaded}
          user={user}
          onLogout={handleLogout}
        />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          onToggleSidebar={() => {
            if (isMobile) {
              setSidebarOpen(!sidebarOpen);
            } else {
              setSidebarCollapsed(!sidebarCollapsed);
            }
          }}
        />
        <MainChat
          activeChat={activeChat}
          onSendMessage={handleSendMessage}
          repositoryLabel={selectedRepo?.full_name ?? null}
          repository={selectedRepo}
          onResync={handleResync}
          resyncing={resyncing}
          resyncError={
            resyncError &&
            resyncError.repoId === selectedRepo?.github_repository_id
              ? resyncError.message
              : null
          }
        />
      </div>
    </div>
  );
}
