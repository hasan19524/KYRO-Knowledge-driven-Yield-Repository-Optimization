"use client";

import { useState, useCallback, useEffect } from "react";
import Sidebar from "./Sidebar";
import MainChat from "./MainChat";
import Topbar from "./Topbar";
import { Chat, getAllChats, saveChat, createChat, addMessageToChat, deleteChat } from "@/lib/storage";
import { RepositorySummary } from "./RepositorySection";

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

export default function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [selectedRepo, setSelectedRepo] = useState<RepositorySummary | null>(null);
  const [isMobile, setIsMobile] = useState(false);

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
      const errorMsg = err instanceof Error ? err.message : "An error occurred";
      appendAssistant(`Error: ${errorMsg}`);
    }
  }, [activeChatId, chats, selectedRepo]);

  const handleDeleteChat = useCallback((id: string) => {
    deleteChat(id);
    setChats(getAllChats());
    if (activeChatId === id) setActiveChatId(null);
  }, [activeChatId]);

  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ background: "#08090b" }}>
      {isMobile && sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60"
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
          width: sidebarCollapsed && !isMobile ? "60px" : "310px",
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
        />
      </div>
    </div>
  );
}
