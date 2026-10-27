import type { ReactNode } from "react";
import AuthBrandPanel from "./AuthBrandPanel";
import AuthFormPanel from "./AuthFormPanel";

interface AuthLayoutProps {
  mode: "login" | "signup";
  children: ReactNode;
}

export default function AuthLayout({ mode, children }: AuthLayoutProps) {
  return (
    <main className="flex min-h-dvh w-full flex-col items-center justify-center bg-background px-4 py-8 sm:px-6 lg:px-8">
      <div className="w-full max-w-[1200px]">
        <div className="grid overflow-hidden rounded-xl border border-border bg-surface shadow-[0_30px_80px_-40px_rgba(0,0,0,0.55)] lg:grid-cols-[1.15fr_1fr]">
          <AuthBrandPanel mode={mode} />
          <AuthFormPanel>{children}</AuthFormPanel>
        </div>
        <footer className="mt-4 flex items-center justify-between gap-4 px-1 font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted">
          <span>KYRO v1.0</span>
          <span className="hidden text-right sm:block">
            Knowledge-driven yield repository optimization
          </span>
        </footer>
      </div>
    </main>
  );
}
