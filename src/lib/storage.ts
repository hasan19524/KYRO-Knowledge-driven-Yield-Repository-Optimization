export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface Chat {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

const STORAGE_KEY = "mind_chats";

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

export function generateTitle(firstMessage: string): string {
  const cleaned = firstMessage.replace(/\n/g, " ").trim();
  if (cleaned.length <= 40) return cleaned;
  return cleaned.slice(0, 40).trimEnd() + "...";
}

export function createChat(firstMessage: string): Chat {
  const now = Date.now();
  return {
    id: generateId(),
    title: generateTitle(firstMessage),
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

export function getAllChats(): Chat[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const chats: Chat[] = JSON.parse(raw);
    return chats.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

export function getChat(id: string): Chat | null {
  const chats = getAllChats();
  return chats.find((c) => c.id === id) || null;
}

export function saveChat(chat: Chat): void {
  if (typeof window === "undefined") return;
  const chats = getAllChats();
  const idx = chats.findIndex((c) => c.id === chat.id);
  if (idx >= 0) {
    chats[idx] = chat;
  } else {
    chats.unshift(chat);
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

export function deleteChat(id: string): void {
  if (typeof window === "undefined") return;
  const chats = getAllChats().filter((c) => c.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

export function addMessageToChat(
  chatId: string,
  message: ChatMessage
): Chat | null {
  const chats = getAllChats();
  const chat = chats.find((c) => c.id === chatId);
  if (!chat) return null;
  chat.messages.push(message);
  chat.updatedAt = Date.now();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
  return chat;
}
