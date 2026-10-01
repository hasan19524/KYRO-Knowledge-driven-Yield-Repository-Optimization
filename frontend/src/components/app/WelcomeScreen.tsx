"use client";

import { Lock } from "lucide-react";
import ChatComposer from "./ChatComposer";
import SuggestionChips from "./SuggestionChips";

function SparkleIcon({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" className={className} style={style}>
      <path
        d="M24 4L27.5 19.5L43 24L27.5 28.5L24 44L20.5 28.5L5 24L20.5 19.5L24 4Z"
        fill="currentColor"
      />
      <path
        d="M38 6L39.2 9.8L43 11L39.2 12.2L38 16L36.8 12.2L33 11L36.8 9.8L38 6Z"
        fill="currentColor"
        opacity="0.6"
      />
    </svg>
  );
}

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
          <SparkleIcon className="h-[52px] w-[52px]" style={{ color: "#4a5060" }} />
        </div>

        <h1
          className="animate-fade-in will-animate delay-100 text-center text-[40px] font-semibold leading-tight tracking-tight sm:text-[44px]"
          style={{ color: "#f5f5f5" }}
        >
          Welcome to <span style={{ color: "#a1a5b0" }}>mind</span>
        </h1>

        <p
          className="animate-fade-in will-animate delay-100 mt-3.5 max-w-[420px] text-center text-[15px] leading-relaxed"
          style={{ color: "#8f96a3" }}
        >
          Your AI workspace for understanding
          <br />
          and building with your codebase.
        </p>

        <div className="animate-fade-in will-animate delay-200 mt-9 w-full">
          <ChatComposer onSend={onSendMessage} repositoryLabel={repositoryLabel} />
        </div>

        <div className="animate-fade-in will-animate delay-300 mt-5">
          <SuggestionChips onSelect={onSendMessage} />
        </div>

        <div className="animate-fade-in will-animate delay-300 mt-14 flex flex-col items-center gap-0.5">
          <div className="flex items-center gap-1.5" style={{ color: "#626977" }}>
            <Lock className="h-3.5 w-3.5" />
            <span className="text-center text-[12px]">
              Your code stays secure and private.
            </span>
          </div>
          <p
            className="text-center text-[12px]"
            style={{ color: "#626977" }}
          >
            Responses are grounded in your repository.
          </p>
        </div>
      </div>
    </div>
  );
}
