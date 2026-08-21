"use client";

import { useEffect, useRef } from "react";
import ChatMessageComponent from "./ChatMessage";
import { ChatMessage } from "@/lib/storage";

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
}

export default function MessageList({ messages, isLoading }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto flex max-w-[900px] flex-col gap-6">
        {messages.map((msg, i) => (
          <ChatMessageComponent key={`${msg.timestamp}-${i}`} message={msg} />
        ))}

        {isLoading && (
          <div className="animate-fade-in will-animate flex gap-3">
            <div
              className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full"
              style={{
                background: "#12151c",
                border: "1px solid rgba(255,255,255,0.08)",
              }}
            >
              <div className="h-3.5 w-3.5 rounded-full" style={{ background: "#626977" }} />
            </div>
            <div className="flex items-center gap-1.5 px-4 py-3">
              <span className="text-[14px]" style={{ color: "#626977" }}>
                mind is thinking
              </span>
              <span className="flex gap-1">
                <span
                  className="h-1 w-1 rounded-full animate-pulse"
                  style={{ background: "#626977", animationDelay: "0ms" }}
                />
                <span
                  className="h-1 w-1 rounded-full animate-pulse"
                  style={{ background: "#626977", animationDelay: "200ms" }}
                />
                <span
                  className="h-1 w-1 rounded-full animate-pulse"
                  style={{ background: "#626977", animationDelay: "400ms" }}
                />
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
