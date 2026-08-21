"use client";

import { ChevronDown, Settings } from "lucide-react";

export default function UserProfile() {
  return (
    <div
      className="flex items-center gap-3 border-t px-3 py-3"
      style={{ borderColor: "rgba(255,255,255,0.08)" }}
    >
      <div
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-[13px] font-semibold"
        style={{
          background: "#1a1e27",
          color: "#8f96a3",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        K
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium" style={{ color: "#f5f5f5" }}>
          Kasif
        </div>
        <div className="text-[11px]" style={{ color: "#626977" }}>
          Free Plan
        </div>
      </div>
      <ChevronDown
        className="h-4 w-4 flex-shrink-0"
        style={{ color: "#626977" }}
      />
      <button
        className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md transition-colors"
        style={{ color: "#626977" }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "#8f96a3")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "#626977")}
        aria-label="Settings"
      >
        <Settings className="h-4 w-4" />
      </button>
    </div>
  );
}
