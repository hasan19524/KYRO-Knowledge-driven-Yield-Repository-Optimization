import KyroLogo from "@/components/app/KyroLogo";
import TechnicalVisualization from "./TechnicalVisualization";

interface AuthBrandPanelProps {
  mode: "login" | "signup";
}

export default function AuthBrandPanel({ mode }: AuthBrandPanelProps) {
  const isLogin = mode === "login";

  return (
    <section
      data-theme="dark"
      className="relative flex flex-col justify-between gap-8 overflow-hidden border-b border-border px-6 py-8 sm:px-10 sm:py-10 lg:border-b-0 lg:border-r lg:px-12 lg:py-12"
      style={{ background: "var(--kyro-bg)" }}
    >
      <div className="flex items-center gap-3">
        <KyroLogo size={34} alt="KYRO" />
        <span className="text-[15px] font-semibold uppercase tracking-[0.16em] text-text">
          KYRO
        </span>
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted">
          {isLogin ? "sign in" : "new workspace"}
        </span>
      </div>

      <div className="flex flex-col gap-6">
        <div className="max-w-[440px]">
          <p
            className="kyro-overline mb-3"
            style={{ color: "var(--kyro-accent-hover)" }}
          >
            {isLogin ? "Repository intelligence" : "Knowledge-driven yield"}
          </p>
          <h2 className="text-[30px] font-semibold leading-[1.15] tracking-[-0.02em] text-text sm:text-[40px]">
            {isLogin ? (
              <>
                Your codebase, <span style={{ color: "var(--kyro-accent-hover)" }}>explained</span>.
              </>
            ) : (
              <>
                Your repository, <span style={{ color: "var(--kyro-accent-hover)" }}>remembered</span>.
              </>
            )}
          </h2>
          <p className="mt-4 max-w-[400px] text-[14px] leading-[1.6] text-text-secondary">
            {isLogin
              ? "Sign in to keep asking questions about code, commits, and architecture — answers grounded in your repository."
              : "Create a workspace, connect a repository, and give every engineer answers grounded in your code."}
          </p>
        </div>

        <TechnicalVisualization mode={mode} className="mx-auto w-full max-w-[440px]" />
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
        <span>index · 12 repos</span>
        <span>graph · 1.2k nodes</span>
        <span>status · ready</span>
      </div>
    </section>
  );
}
