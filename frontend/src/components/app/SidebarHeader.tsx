"use client";

import { Plus, ChevronsLeft, ChevronsRight } from "lucide-react";
import KyroLogo from "./KyroLogo";

interface SidebarHeaderProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNewChat: () => void;
}

export default function SidebarHeader({
  collapsed,
  onToggleCollapse,
  onNewChat,
}: SidebarHeaderProps) {
  return (
    <div className="flex flex-col gap-3 px-3 pt-4 pb-3">
      <div className="flex h-8 items-center justify-between px-[6px]">
        {!collapsed && (
          <div className="flex items-center gap-[9px]">
            <KyroLogo size={26} />
            <span
              className="text-[18px] font-semibold leading-none"
              style={{ color: "var(--kyro-text)", letterSpacing: "0.06em" }}
            >
              KYRO
            </span>
          </div>
        )}

        <button
          onClick={onToggleCollapse}
          className="flex h-7 w-7 items-center justify-center rounded-md transition-colors"
          style={{ color: "var(--kyro-text-muted)" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--kyro-text)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "var(--kyro-text-muted)")}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronsRight className="h-4 w-4" />
          ) : (
            <ChevronsLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {!collapsed && (
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] font-medium transition-colors"
          style={{
            background: "var(--kyro-accent)",
            color: "var(--kyro-text)",
            border: "1px solid transparent",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--kyro-accent-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "var(--kyro-accent)")}
        >
          <Plus className="h-4 w-4" style={{ color: "var(--kyro-text)" }} />
          <span className="flex-1">New chat</span>
          <kbd
            className="rounded px-1.5 py-0.5 font-mono text-[10px]"
            style={{
              border: "1px solid rgba(234,231,220,0.24)",
              color: "rgba(234,231,220,0.72)",
            }}
          >
            ⌘K
          </kbd>
        </button>
      )}

      {collapsed && (
        <div className="flex justify-center">
          <button
            onClick={onNewChat}
            className="flex h-8 w-8 items-center justify-center rounded-md transition-colors"
            style={{
              background: "var(--kyro-accent)",
              color: "var(--kyro-text)",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--kyro-accent-hover)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "var(--kyro-accent)")}
            aria-label="New chat"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
