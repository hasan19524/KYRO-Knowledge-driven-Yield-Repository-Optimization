"use client";

import { useState, useCallback, useEffect } from "react";
import Sidebar from "./Sidebar";
import MainChat from "./MainChat";
import Topbar from "./Topbar";
import { Chat, getAllChats, saveChat, createChat, addMessageToChat, deleteChat } from "@/lib/storage";

export default function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  useEffect(() => {
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

    const allMessages = [...(currentChat?.messages || []), userMsg];

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: allMessages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to get response");

      const assistantMsg = { role: "assistant" as const, content: data.content, timestamp: Date.now() };
      addMessageToChat(currentChat!.id, assistantMsg);
      setChats(getAllChats());
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "An error occurred";
      const errMsg = { role: "assistant" as const, content: `Error: ${errorMsg}`, timestamp: Date.now() };
      addMessageToChat(currentChat!.id, errMsg);
      setChats(getAllChats());
    }
  }, [activeChatId, chats]);

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
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          onNewChat={handleNewChat}
          onSelectChat={handleSelectChat}
          onDeleteChat={handleDeleteChat}
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
        />
      </div>
    </div>
  );
}
