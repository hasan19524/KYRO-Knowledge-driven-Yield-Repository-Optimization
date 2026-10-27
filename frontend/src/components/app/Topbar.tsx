"use client";

import { PanelLeft } from "lucide-react";
import GithubIcon from "@/components/icons/GithubIcon";

interface TopbarProps {
  onToggleSidebar: () => void;
}

export default function Topbar({ onToggleSidebar }: TopbarProps) {
  return (
    <header
      className="flex h-14 flex-shrink-0 items-center justify-between gap-3 border-b px-4 sm:px-6"
      style={{ borderColor: "var(--kyro-border)", background: "var(--kyro-bg)" }}
    >
      <button
        onClick={onToggleSidebar}
        className="flex h-8 w-8 items-center justify-center rounded-md transition-colors lg:hidden"
        style={{ color: "var(--kyro-text-secondary)" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--kyro-accent-soft)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        aria-label="Toggle sidebar"
        type="button"
      >
        <PanelLeft className="h-4 w-4" />
      </button>

      <div className="flex flex-1 items-center justify-end gap-2.5">
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          className="flex h-8 w-8 items-center justify-center rounded-md transition-colors"
          style={{ color: "var(--kyro-text-muted)" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--kyro-accent-soft)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          aria-label="GitHub"
        >
          <GithubIcon className="h-[18px] w-[18px]" />
        </a>
      </div>
    </header>
  );
}
