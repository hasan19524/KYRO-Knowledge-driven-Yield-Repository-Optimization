"use client";

import { Plus, ChevronsLeft, ChevronsRight } from "lucide-react";

function SparkleLogo({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} style={style}>
      <path
        d="M12 2L14 9L21 12L14 15L12 22L10 15L3 12L10 9L12 2Z"
        fill="currentColor"
      />
      <path
        d="M19 3L19.8 5.4L22 6.2L19.8 7L19 9.4L18.2 7L16 6.2L18.2 5.4L19 3Z"
        fill="currentColor"
        opacity="0.5"
      />
    </svg>
  );
}

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
    <div className="flex flex-col gap-3 px-3 pt-4 pb-2">
      <div className="flex items-center justify-between">
        {!collapsed && (
          <div className="flex items-center gap-2.5">
            <SparkleLogo className="h-[22px] w-[22px] flex-shrink-0" style={{ color: "#d0d4dc" }} />
            <div className="flex flex-col">
              <span className="text-[15px] font-semibold leading-tight tracking-tight" style={{ color: "#f5f5f5" }}>
                mind
              </span>
              <span className="text-[11px] leading-tight" style={{ color: "#626977" }}>
                AI Repository Intelligence
              </span>
            </div>
          </div>
        )}

        <button
          onClick={onToggleCollapse}
          className="flex h-7 w-7 items-center justify-center rounded-md transition-colors"
          style={{ color: "#626977" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#8f96a3")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#626977")}
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
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] font-medium transition-colors"
          style={{
            background: "#12151c",
            border: "1px solid rgba(255,255,255,0.08)",
            color: "#f5f5f5",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#1a1e27")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "#12151c")}
        >
          <Plus className="h-4 w-4" style={{ color: "#8f96a3" }} />
          <span className="flex-1">New chat</span>
          <kbd
            className="rounded px-1.5 py-0.5 font-mono text-[10px]"
            style={{
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#626977",
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
            className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
            style={{
              background: "#12151c",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#8f96a3",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#1a1e27")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "#12151c")}
            aria-label="New chat"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
