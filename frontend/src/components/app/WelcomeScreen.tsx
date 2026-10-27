"use client";

import { Lock } from "lucide-react";
import ChatComposer from "./ChatComposer";
import SuggestionChips from "./SuggestionChips";
import KyroLogo from "./KyroLogo";

interface WelcomeScreenProps {
  onSendMessage: (content: string) => void;
  repositoryLabel: string | null;
}

export default function WelcomeScreen({
  onSendMessage,
  repositoryLabel,
}: WelcomeScreenProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-5 pb-20">
      <div className="flex w-full max-w-[900px] flex-col items-center">
        <div className="mb-5 animate-fade-in will-animate">
          <KyroLogo size={64} />
        </div>

        <h1
          className="animate-fade-in will-animate delay-100 text-center text-[24px] font-semibold leading-tight sm:text-[28px]"
          style={{ color: "var(--kyro-text)", letterSpacing: "-0.02em" }}
        >
          Welcome to KYRO
        </h1>

        <p
          className="animate-fade-in will-animate delay-100 mt-3 max-w-[440px] text-center text-[14px] leading-relaxed"
          style={{ color: "var(--kyro-text-muted)" }}
        >
          Your AI workspace for understanding
          <br />
          and building with your codebase.
        </p>

        <div className="animate-fade-in will-animate delay-200 mt-8 w-full">
          <ChatComposer onSend={onSendMessage} repositoryLabel={repositoryLabel} />
        </div>

        <div className="animate-fade-in will-animate delay-300 mt-5">
          <SuggestionChips onSelect={onSendMessage} />
        </div>

        <div className="animate-fade-in will-animate delay-300 mt-14 flex flex-col items-center gap-0.5">
          <div className="flex items-center gap-1.5" style={{ color: "var(--kyro-text-muted)" }}>
            <Lock className="h-3.5 w-3.5" />
            <span className="text-center text-[12px]">
              Your code stays secure and private.
            </span>
          </div>
          <p
            className="text-center text-[12px]"
            style={{ color: "var(--kyro-text-muted)" }}
          >
            Responses are grounded in your repository.
          </p>
        </div>
      </div>
    </div>
  );
}
