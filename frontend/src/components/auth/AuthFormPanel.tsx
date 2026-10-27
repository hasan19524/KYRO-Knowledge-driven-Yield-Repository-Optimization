import type { ReactNode } from "react";

interface AuthFormPanelProps {
  children: ReactNode;
}

export default function AuthFormPanel({ children }: AuthFormPanelProps) {
  return (
    <section
      data-theme="light"
      className="relative flex flex-col justify-center overflow-hidden bg-background px-6 py-10 sm:px-10 lg:px-14 lg:py-14"
    >
      <svg
        aria-hidden="true"
        focusable="false"
        viewBox="0 0 200 200"
        fill="none"
        className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 text-border"
      >
        <circle cx="100" cy="100" r="99" stroke="currentColor" strokeWidth="1" />
        <circle cx="100" cy="100" r="68" stroke="currentColor" strokeWidth="1" />
      </svg>

      <div className="relative mx-auto flex w-full max-w-[420px] flex-col gap-6">
        {children}
      </div>
    </section>
  );
}
