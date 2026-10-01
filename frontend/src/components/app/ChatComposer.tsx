"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Paperclip, Folder, ChevronDown, ArrowUp } from "lucide-react";

interface ChatComposerProps {
  onSend: (content: string) => void;
  initialValue?: string;
  repositoryLabel?: string | null;
}

function SparkleSmall({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} style={style}>
      <path
        d="M8 1L9.5 6.5L15 8L9.5 9.5L8 15L6.5 9.5L1 8L6.5 6.5L8 1Z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function ChatComposer({
  onSend,
  initialValue = "",
  repositoryLabel,
}: ChatComposerProps) {
  const [value, setValue] = useState(initialValue);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  useEffect(() => {
    if (initialValue && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [initialValue]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div
      className="w-full transition-colors"
      style={{
        background: "#12151c",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: "14px",
        maxWidth: "900px",
      }}
    >
      <div className="flex items-start gap-2 px-5 pt-5 pb-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about your repository..."
          rows={4}
          className="max-h-[200px] min-h-[80px] flex-1 bg-transparent py-1 text-[15px] leading-[1.6] outline-none placeholder:text-[#626977]"
          style={{ color: "#f5f5f5", resize: "none" }}
        />
      </div>

      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div className="flex items-center gap-2">
          <button
            className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
            style={{ color: "#626977" }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = "#8f96a3";
              e.currentTarget.style.background = "#1a1e27";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "#626977";
              e.currentTarget.style.background = "transparent";
            }}
            aria-label="Attach context"
            type="button"
          >
            <Paperclip className="h-4 w-4" />
          </button>

          <button
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] transition-colors"
            style={{
              background: "#1a1e27",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#8f96a3",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.12)")}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)")}
            type="button"
          >
            <Folder className="h-3.5 w-3.5" style={{ color: "#626977" }} />
            <span className="max-w-[180px] truncate">
              {repositoryLabel ?? "Repository"}
            </span>
            <ChevronDown className="h-3 w-3" style={{ color: "#626977" }} />
          </button>

          <button
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] transition-colors"
            style={{
              background: "#1a1e27",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#8f96a3",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.12)")}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)")}
            type="button"
          >
            <SparkleSmall className="h-3.5 w-3.5" style={{ color: "#626977" }} />
            <span>Auto</span>
            <ChevronDown className="h-3 w-3" style={{ color: "#626977" }} />
          </button>
        </div>

        <button
          onClick={handleSubmit}
          disabled={!value.trim()}
          className="flex h-9 w-9 items-center justify-center rounded-full transition-all disabled:opacity-20 disabled:cursor-not-allowed"
          style={{
            background: value.trim() ? "#f5f5f5" : "#2a2d35",
            color: value.trim() ? "#08090b" : "#626977",
          }}
          onMouseEnter={(e) => {
            if (value.trim()) e.currentTarget.style.background = "#e5e5e5";
          }}
          onMouseLeave={(e) => {
            if (value.trim()) e.currentTarget.style.background = "#f5f5f5";
          }}
          aria-label="Send message"
          type="button"
        >
          <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
}
