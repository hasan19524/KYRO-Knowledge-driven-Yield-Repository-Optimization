"use client";

import { Sparkles, Copy, Check } from "lucide-react";
import { useState } from "react";
import { ChatMessage } from "@/lib/storage";

interface ChatMessageProps {
  message: ChatMessage;
}

function CodeBlock({ language, children }: { language?: string; children: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="group relative my-3 rounded-lg overflow-hidden" style={{ background: "#0b0d12" }}>
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <span className="text-[11px]" style={{ color: "#626977" }}>
          {language || "code"}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-2 py-0.5 text-[11px] transition-colors opacity-0 group-hover:opacity-100"
          style={{ color: "#626977" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#8f96a3")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#626977")}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-[13px] leading-relaxed">
        <code style={{ color: "#c8cdd6", fontFamily: "var(--font-geist-mono), ui-monospace, monospace" }}>
          {children}
        </code>
      </pre>
    </div>
  );
}

function parseMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      parts.push(
        <CodeBlock key={parts.length} language={lang}>
          {codeLines.join("\n")}
        </CodeBlock>
      );
      continue;
    }

    if (line.startsWith("### ")) {
      parts.push(
        <h3
          key={parts.length}
          className="mt-4 mb-2 text-[15px] font-semibold"
          style={{ color: "#f5f5f5" }}
        >
          {line.slice(4)}
        </h3>
      );
      i++;
      continue;
    }

    if (line.startsWith("## ")) {
      parts.push(
        <h2
          key={parts.length}
          className="mt-5 mb-2 text-[17px] font-semibold"
          style={{ color: "#f5f5f5" }}
        >
          {line.slice(3)}
        </h2>
      );
      i++;
      continue;
    }

    if (line.startsWith("# ")) {
      parts.push(
        <h1
          key={parts.length}
          className="mt-6 mb-3 text-[20px] font-bold"
          style={{ color: "#f5f5f5" }}
        >
          {line.slice(2)}
        </h1>
      );
      i++;
      continue;
    }

    if (line.startsWith("- ") || line.startsWith("* ")) {
      const listItems: string[] = [];
      while (i < lines.length && (lines[i].startsWith("- ") || lines[i].startsWith("* "))) {
        listItems.push(lines[i].slice(2));
        i++;
      }
      parts.push(
        <ul key={parts.length} className="my-2 list-disc pl-5 space-y-1">
          {listItems.map((item, idx) => (
            <li key={idx} className="text-[14px] leading-relaxed" style={{ color: "#c8cdd6" }}>
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
      continue;
    }

    if (/^\d+\.\s/.test(line)) {
      const listItems: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        listItems.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      parts.push(
        <ol key={parts.length} className="my-2 list-decimal pl-5 space-y-1">
          {listItems.map((item, idx) => (
            <li key={idx} className="text-[14px] leading-relaxed" style={{ color: "#c8cdd6" }}>
              {renderInline(item)}
            </li>
          ))}
        </ol>
      );
      continue;
    }

    if (line.trim() === "") {
      parts.push(<div key={parts.length} className="h-2" />);
      i++;
      continue;
    }

    parts.push(
      <p key={parts.length} className="my-1 text-[14px] leading-relaxed" style={{ color: "#c8cdd6" }}>
        {renderInline(line)}
      </p>
    );
    i++;
  }

  return parts;
}

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const regex = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*/g;
  let lastIndex = 0;
  let match;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    if (match[1]) {
      parts.push(
        <code
          key={key++}
          className="rounded px-1.5 py-0.5 text-[13px]"
          style={{ background: "#1a1e27", color: "#c8cdd6" }}
        >
          {match[1]}
        </code>
      );
    } else if (match[2]) {
      parts.push(
        <strong key={key++} className="font-semibold" style={{ color: "#f5f5f5" }}>
          {match[2]}
        </strong>
      );
    } else if (match[3]) {
      parts.push(
        <em key={key++} className="italic">
          {match[3]}
        </em>
      );
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

export default function ChatMessageComponent({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={`animate-fade-in will-animate flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div
          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full"
          style={{
            background: "#12151c",
            border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <Sparkles className="h-3.5 w-3.5" style={{ color: "#626977" }} />
        </div>
      )}

      <div
        className={`max-w-[75%] rounded-xl px-4 py-3 ${
          isUser ? "text-[14px]" : ""
        }`}
        style={
          isUser
            ? {
                background: "#1a1e27",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "#f5f5f5",
              }
            : { color: "#c8cdd6" }
        }
      >
        {isUser ? (
          <p className="text-[14px] leading-relaxed">{message.content}</p>
        ) : (
          <div>{parseMarkdown(message.content)}</div>
        )}
      </div>
    </div>
  );
}
