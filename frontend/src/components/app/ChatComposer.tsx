"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Paperclip, Folder, ChevronDown, ArrowUp } from "lucide-react";

interface ChatComposerProps {
  onSend: (content: string) => void;
  initialValue?: string;
  repositoryLabel?: string | null;
  /** True while a query is in flight — blocks duplicate submissions. */
  busy?: boolean;
  /** True while the selected repository cannot answer (indexing/failed/revoked). */
  disabled?: boolean;
  /** Placeholder shown while disabled — tells the user why input is locked. */
  disabledReason?: string;
}

function SparkleSmall({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} style={style}>
      <path
        d="M8 1L9.5 6.5L15 8L9.5 9.5L8 15L6.5 9.5L1 8L6.5 9.5L8 1Z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function ChatComposer({
  onSend,
  initialValue = "",
  repositoryLabel,
  busy = false,
  disabled = false,
  disabledReason,
}: ChatComposerProps) {
  const [value, setValue] = useState(initialValue);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // One gate for styling + submission: locked composer never sends.
  const canSend = value.trim() !== "" && !busy && !disabled;

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
    if (!trimmed || busy || disabled) return; // ignore while locked or in flight
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
      className="w-full border border-border transition-colors focus-within:border-accent-hover"
      style={{
        background: "var(--kyro-card)",
        borderRadius: "12px",
        maxWidth: "900px",
      }}
    >
      <div className="flex items-start gap-2 px-5 pt-5 pb-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={
            disabled
              ? (disabledReason ?? "KYRO is indexing this repository…")
              : "Ask KYRO anything..."
          }
          rows={4}
          className="max-h-[200px] min-h-[76px] flex-1 bg-transparent py-1 text-[14px] leading-[1.6] outline-none disabled:cursor-not-allowed"
          style={{
            color: disabled ? "var(--kyro-text-muted)" : "var(--kyro-text)",
            resize: "none",
          }}
        />
      </div>

      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderTop: "1px solid var(--kyro-border-subtle)" }}
      >
        <div
          className="flex items-center gap-2"
          style={disabled ? { opacity: 0.4, pointerEvents: "none" } : undefined}
        >
          <button
            className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
            style={{ color: "var(--kyro-text-muted)" }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = "var(--kyro-text-secondary)";
              e.currentTarget.style.background = "var(--kyro-card-hover)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "var(--kyro-text-muted)";
              e.currentTarget.style.background = "transparent";
            }}
            aria-label="Attach context"
            type="button"
          >
            <Paperclip className="h-4 w-4" />
          </button>

          <button
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] transition-colors"
            style={{
              background: "transparent",
              border: "1px solid var(--kyro-border)",
              color: "var(--kyro-text-secondary)",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--kyro-accent-soft)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            type="button"
          >
            <Folder className="h-3.5 w-3.5" style={{ color: "var(--kyro-text-muted)" }} />
            <span>{repositoryLabel ?? "Repository"}</span>
            <ChevronDown className="h-3 w-3" style={{ color: "var(--kyro-text-muted)" }} />
          </button>

          <button
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] transition-colors"
            style={{
              background: "transparent",
              border: "1px solid var(--kyro-border)",
              color: "var(--kyro-text-secondary)",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--kyro-accent-soft)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            type="button"
          >
            <SparkleSmall className="h-3.5 w-3.5" style={{ color: "var(--kyro-text-muted)" }} />
            <span>Auto</span>
            <ChevronDown className="h-3 w-3" style={{ color: "var(--kyro-text-muted)" }} />
          </button>
        </div>

        <button
          onClick={handleSubmit}
          disabled={!canSend}
          className="flex h-9 w-9 items-center justify-center rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          style={{
            background: canSend ? "var(--kyro-accent)" : "var(--kyro-card-active)",
            color: canSend ? "var(--kyro-text)" : "var(--kyro-text-muted)",
          }}
          onMouseEnter={(e) => {
            if (canSend) e.currentTarget.style.background = "var(--kyro-accent-hover)";
          }}
          onMouseLeave={(e) => {
            if (canSend) e.currentTarget.style.background = "var(--kyro-accent)";
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
