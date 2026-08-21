"use client";

import { useState, useMemo } from "react";
import SidebarHeader from "./SidebarHeader";
import ChatHistory from "./ChatHistory";
import RepositorySection from "./RepositorySection";
import UserProfile from "./UserProfile";
import { Chat } from "@/lib/storage";

interface SidebarProps {
  chats: Chat[];
  activeChatId: string | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
}

export default function Sidebar({
  chats,
  activeChatId,
  collapsed,
  onToggleCollapse,
  onNewChat,
  onSelectChat,
  onDeleteChat,
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
        background: "#0b0d12",
        borderColor: "rgba(255,255,255,0.08)",
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

          <RepositorySection />
          <UserProfile />
        </>
      )}
    </div>
  );
}
