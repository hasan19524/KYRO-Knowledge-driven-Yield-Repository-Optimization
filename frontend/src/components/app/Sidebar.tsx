"use client";

import { useState, useMemo } from "react";
import SidebarHeader from "./SidebarHeader";
import ChatHistory from "./ChatHistory";
import RepositorySection, { RepositorySummary } from "./RepositorySection";
import UserProfile from "./UserProfile";
import { Chat } from "@/lib/storage";
import { AuthUser } from "@/lib/auth";

interface SidebarProps {
  chats: Chat[];
  activeChatId: string | null;
  collapsed: boolean;
  selectedRepositoryId: number | null;
  onToggleCollapse: () => void;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onSelectRepository: (repo: RepositorySummary) => void;
  /** Forwarded to RepositorySection: fresh repo list after every poll. */
  onRepositoriesLoaded: (repos: RepositorySummary[]) => void;
  user: AuthUser | null;
  onLogout: () => void;
}

export default function Sidebar({
  chats,
  activeChatId,
  collapsed,
  selectedRepositoryId,
  onToggleCollapse,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  onSelectRepository,
  onRepositoriesLoaded,
  user,
  onLogout,
}: SidebarProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredChats = useMemo(() => {
    if (!searchQuery.trim()) return chats;
    const q = searchQuery.toLowerCase();
    return chats.filter((c) => c.title.toLowerCase().includes(q));
  }, [chats, searchQuery]);

  return (
    <div
      className="flex h-full flex-col border-r"
      style={{
        background: "var(--kyro-surface)",
        borderColor: "var(--kyro-border)",
        width: "100%",
      }}
    >
      <SidebarHeader
        collapsed={collapsed}
        onToggleCollapse={onToggleCollapse}
        onNewChat={onNewChat}
      />

      {!collapsed && (
        <>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-3">
            <div className="flex-1 overflow-y-auto pb-2">
              <ChatHistory
                chats={filteredChats}
                activeChatId={activeChatId}
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                onSelectChat={onSelectChat}
                onDeleteChat={onDeleteChat}
              />
            </div>
          </div>

          <RepositorySection
            selectedId={selectedRepositoryId}
            onSelect={onSelectRepository}
            onRepositoriesLoaded={onRepositoriesLoaded}
          />
          <UserProfile user={user} onLogout={onLogout} />
        </>
      )}
    </div>
  );
}
