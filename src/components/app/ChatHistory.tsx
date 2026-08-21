"use client";

import { Search, MessageSquare, Trash2 } from "lucide-react";
import { Chat } from "@/lib/storage";

interface ChatHistoryProps {
  chats: Chat[];
  activeChatId: string | null;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
}

function groupChats(chats: Chat[]): { label: string; items: Chat[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);

  const groups: { label: string; items: Chat[] }[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Previous 7 days", items: [] },
  ];

  for (const chat of chats) {
    const d = new Date(chat.updatedAt);
    if (d >= today) {
      groups[0].items.push(chat);
    } else if (d >= yesterday) {
      groups[1].items.push(chat);
    } else if (d >= weekAgo) {
      groups[2].items.push(chat);
    }
  }

  return groups.filter((g) => g.items.length > 0);
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const chatDate = new Date(d.getFullYear(), d.getMonth(), d.getDate());

  if (chatDate.getTime() === today.getTime()) {
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  }

  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (chatDate.getTime() === yesterday.getTime()) {
    return "Yesterday";
  }

  const diffDays = Math.floor((today.getTime() - chatDate.getTime()) / 86400000);
  if (diffDays < 7) return `${diffDays} days ago`;

  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function ChatHistory({
  chats,
  activeChatId,
  searchQuery,
  onSearchChange,
  onSelectChat,
  onDeleteChat,
}: ChatHistoryProps) {
  const groups = groupChats(chats);

  return (
    <>
      <div className="relative mb-4">
        <Search
          className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2"
          style={{ color: "#626977" }}
        />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search chats..."
          className="w-full rounded-lg py-2 pl-8 pr-8 text-[13px] outline-none transition-colors"
          style={{
            background: "#12151c",
            border: "1px solid rgba(255,255,255,0.08)",
            color: "#f5f5f5",
          }}
          onFocus={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.12)")}
          onBlur={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)")}
        />
        <kbd
          className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded px-1.5 py-0.5 font-mono text-[10px]"
          style={{
            border: "1px solid rgba(255,255,255,0.08)",
            color: "#626977",
          }}
        >
          ⌘F
        </kbd>
      </div>

      {groups.map((group) => (
        <div key={group.label} className="mb-4">
          <div
            className="mb-1.5 px-1 text-[11px] font-medium"
            style={{ color: "#626977" }}
          >
            {group.label}
          </div>
          <div className="flex flex-col">
            {group.items.map((chat) => (
              <div
                key={chat.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelectChat(chat.id)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectChat(chat.id); } }}
                className="group flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-left transition-colors"
                style={{
                  background: activeChatId === chat.id ? "#1a1e27" : "transparent",
                  color: activeChatId === chat.id ? "#f5f5f5" : "#8f96a3",
                }}
                onMouseEnter={(e) => {
                  if (activeChatId !== chat.id) e.currentTarget.style.background = "#12151c";
                }}
                onMouseLeave={(e) => {
                  if (activeChatId !== chat.id) e.currentTarget.style.background = "transparent";
                }}
              >
                <MessageSquare
                  className="h-4 w-4 flex-shrink-0"
                  style={{ color: "#626977" }}
                />
                <span className="flex-1 truncate text-[13px]">{chat.title}</span>
                <span
                  className="flex-shrink-0 text-[11px]"
                  style={{ color: "#626977" }}
                >
                  {formatTime(chat.updatedAt)}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteChat(chat.id);
                  }}
                  className="flex-shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                  style={{ color: "#626977" }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = "#ef4444")}
                  onMouseLeave={(e) => (e.currentTarget.style.color = "#626977")}
                  aria-label="Delete chat"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}

      {chats.length === 0 && !searchQuery && (
        <div className="px-1 py-6 text-center text-[12px]" style={{ color: "#626977" }}>
          No chats yet. Start a new conversation.
        </div>
      )}
    </>
  );
}
