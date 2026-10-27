"use client";

import Link from "next/link";
import { ArrowRight, LoaderCircle } from "lucide-react";
import GithubIcon from "@/components/icons/GithubIcon";

interface PrimaryButtonProps {
  loading: boolean;
  loadingLabel: string;
  children: React.ReactNode;
}

export function PrimaryButton({ loading, loadingLabel, children }: PrimaryButtonProps) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="group flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-[#304d3a] px-4 text-[13px] font-medium leading-none text-[#eae7dc] transition-colors hover:bg-[#5f795f] disabled:cursor-not-allowed disabled:opacity-60"
    >
      {loading ? (
        <>
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
          {loadingLabel}
        </>
      ) : (
        <>
          {children}
          <ArrowRight
            className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </>
      )}
    </button>
  );
}

/**
 * "Sign in with GitHub" — a full-page navigation to the backend's OAuth
 * /start endpoint (the proxy forwards it; GitHub redirects back to
 * /backend/api/auth/github/callback which lands on /app with a session).
 */
export function GithubSignInButton() {
  return (
    <button
      type="button"
      onClick={() => {
        // Full-page navigation is required: the destination is a proxy route
        // whose backend answers with a 302 that leaves this origin (GitHub's
        // authorize page) — client-side routing cannot follow that chain.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = "/backend/api/auth/github/start";
      }}
      className="flex h-12 w-full items-center justify-center gap-2.5 rounded-lg border border-[#3a4149] bg-transparent px-4 text-[13px] font-medium leading-none text-text transition-colors hover:bg-[#1c2127]"
    >
      <GithubIcon className="h-4 w-4" />
      Sign in with GitHub
    </button>
  );
}

/** Visual "or" divider between the password form and the GitHub button. */
export function AuthDivider() {
  return (
    <div className="flex items-center gap-3" aria-hidden="true">
      <div className="h-px flex-1 bg-[#2a2e34]" />
      <span className="text-[11px] uppercase tracking-[0.08em] text-text-secondary">
        or
      </span>
      <div className="h-px flex-1 bg-[#2a2e34]" />
    </div>
  );
}

interface AuthSwitchLinkProps {
  prompt: string;
  href: string;
  action: string;
}

export function AuthSwitchLink({ prompt, href, action }: AuthSwitchLinkProps) {
  return (
    <p className="text-center text-[13px] leading-[1.5] text-text-secondary">
      {prompt}{" "}
      <Link
        href={href}
        className="font-medium text-accent underline-offset-4 transition-colors hover:text-accent-hover hover:underline"
      >
        {action}
      </Link>
    </p>
  );
}
