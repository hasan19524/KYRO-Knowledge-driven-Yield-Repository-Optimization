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
    <div className="flex flex-wrap items-center justify-center gap-2.5">
      {suggestions.map((s) => (
        <button
          key={s.text}
          onClick={() => onSelect(s.text)}
          className="flex items-center gap-2 rounded-full px-4 py-2.5 text-[13px] transition-all"
          style={{
            background: "transparent",
            border: "1px solid rgba(255,255,255,0.08)",
            color: "#8f96a3",
            borderRadius: "9999px",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.14)";
            e.currentTarget.style.background = "#12151c";
            e.currentTarget.style.color = "#f5f5f5";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)";
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.color = "#8f96a3";
          }}
          type="button"
        >
          <s.icon className="h-4 w-4 flex-shrink-0" style={{ color: "#626977" }} />
          <span className="whitespace-nowrap">{s.text}</span>
        </button>
      ))}
    </div>
  );
}
