"use client";

import { Code, Clock, AlertTriangle, Shield } from "lucide-react";

interface SuggestionChipsProps {
  onSelect: (text: string) => void;
}

const suggestions = [
  { icon: Code, text: "Explain this codebase" },
  { icon: Clock, text: "What changed recently?" },
  { icon: AlertTriangle, text: "Find potential issues" },
  { icon: Shield, text: "How does authentication work?" },
];

export default function SuggestionChips({ onSelect }: SuggestionChipsProps) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-2">
      {suggestions.map((s) => (
        <button
          key={s.text}
          onClick={() => onSelect(s.text)}
          className="flex items-center gap-2 rounded-md px-3.5 py-2 text-[13px] transition-colors"
          style={{
            background: "transparent",
            border: "1px solid var(--kyro-border)",
            color: "var(--kyro-text-secondary)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--kyro-accent-hover)";
            e.currentTarget.style.background = "var(--kyro-accent-soft)";
            e.currentTarget.style.color = "var(--kyro-text)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--kyro-border)";
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "var(--kyro-text-secondary)";
          }}
          type="button"
        >
          <s.icon className="h-4 w-4 flex-shrink-0" style={{ color: "var(--kyro-text-muted)" }} />
          <span className="whitespace-nowrap">{s.text}</span>
        </button>
      ))}
    </div>
  );
}
