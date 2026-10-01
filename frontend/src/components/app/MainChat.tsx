"use client";

import { useState, useCallback } from "react";
import WelcomeScreen from "./WelcomeScreen";
import MessageList from "./MessageList";
import ChatComposer from "./ChatComposer";
import { Chat } from "@/lib/storage";

interface MainChatProps {
  activeChat: Chat | null;
  onSendMessage: (content: string) => void;
  repositoryLabel: string | null;
}

export default function MainChat({
  activeChat,
  onSendMessage,
  repositoryLabel,
}: MainChatProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = useCallback(async (content: string) => {
    setIsLoading(true);
    try {
      await onSendMessage(content);
    } finally {
      setIsLoading(false);
    }
  }, [onSendMessage]);

  const hasMessages = activeChat && activeChat.messages.length > 0;

  return (
    <div className="flex flex-1 flex-col overflow-hidden" style={{ background: "#08090b" }}>
      {hasMessages ? (
        <>
          <MessageList messages={activeChat.messages} isLoading={isLoading} />
          <div
            className="flex justify-center px-4 pb-4 pt-2"
          >
            <div className="w-full max-w-[900px]">
              <ChatComposer onSend={handleSend} repositoryLabel={repositoryLabel} />
            </div>
          </div>
        </>
      ) : (
        <WelcomeScreen
          onSendMessage={handleSend}
          repositoryLabel={repositoryLabel}
        />
      )}
    </div>
  );
}
