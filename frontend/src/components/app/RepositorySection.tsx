"use client";

import { Folder, Plus } from "lucide-react";

export default function RepositorySection() {
  return (
    <div
      className="mx-3 mb-2 rounded-lg px-3 py-3"
      style={{
        background: "#12151c",
        border: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <div className="mb-2.5 flex items-center justify-between">
        <span
          className="text-[11px] font-medium"
          style={{ color: "#626977" }}
        >
          Repositories
        </span>
        <button
          className="flex h-5 w-5 items-center justify-center rounded transition-colors"
          style={{ color: "#626977" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#8f96a3")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#626977")}
          aria-label="Add repository"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex items-center gap-2.5">
        <div
          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md"
          style={{
            background: "#1a1e27",
            border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <Folder className="h-3.5 w-3.5" style={{ color: "#8f96a3" }} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-medium" style={{ color: "#f5f5f5" }}>
            mind-ai/repo
          </div>
          <div className="text-[11px]" style={{ color: "#626977" }}>
            2,842 files indexed
          </div>
        </div>
        <div
          className="h-2 w-2 flex-shrink-0 rounded-full"
          style={{ background: "#22c55e" }}
        />
      </div>
    </div>
  );
}
