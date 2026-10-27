"use client";

import { ChevronDown, LogOut, Settings } from "lucide-react";
import { AuthUser } from "@/lib/auth";

interface UserProfileProps {
  user: AuthUser | null;
  onLogout: () => void;
}

export default function UserProfile({ user, onLogout }: UserProfileProps) {
  const name = user?.handle ?? "Not signed in";
  const initial = (user?.handle ?? "?").charAt(0).toUpperCase();

  return (
    <div
      className="flex items-center gap-3 border-t px-3 py-3"
      style={{ borderColor: "var(--kyro-border)" }}
    >
      <div
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-[13px] font-medium"
        style={{
          background: "var(--kyro-accent-soft)",
          color: "var(--kyro-text)",
          border: "1px solid var(--kyro-sage-soft)",
        }}
      >
        {initial}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium" style={{ color: "var(--kyro-text)" }}>
          {name}
        </div>
        <div className="text-[11px]" style={{ color: "var(--kyro-text-muted)" }}>
          {user?.email ?? "KYRO"}
        </div>
      </div>
      <ChevronDown
        className="h-4 w-4 flex-shrink-0"
        style={{ color: "var(--kyro-text-muted)" }}
      />
      <button
        className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md transition-colors"
        style={{ color: "var(--kyro-text-muted)" }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--kyro-text-secondary)")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--kyro-text-muted)")}
        aria-label="Settings"
        type="button"
      >
        <Settings className="h-4 w-4" />
      </button>
      <button
        className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md transition-colors"
        style={{ color: "var(--kyro-text-muted)" }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--kyro-error)")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--kyro-text-muted)")}
        aria-label="Log out"
        onClick={onLogout}
        type="button"
      >
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}
