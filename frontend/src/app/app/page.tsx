"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/app/AppShell";
import { AuthUser, SessionCheck, checkSession } from "@/lib/auth";

export default function AppPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    checkSession().then((result: SessionCheck) => {
      if (cancelled) return;
      if (result.state === "unauthenticated") {
        // Real 401 only: the session is gone, go through the login flow.
        router.replace("/login");
        return;
      }
      if (result.state === "error") {
        // Backend outage / 5xx: NOT a logout. Stay here and offer a retry.
        setError(result.message);
        return;
      }
      setError(null); // authenticated — clear any prior outage error
      setUser(result.user);
      setChecked(true);
    });
    return () => {
      cancelled = true;
    };
  }, [router, attempt]);

  if (error) {
    return (
      <div
        className="flex h-screen flex-col items-center justify-center gap-4"
        style={{ background: "var(--kyro-bg)" }}
        role="alert"
      >
        <p className="text-[15px]" style={{ color: "var(--kyro-text)" }}>
          KYRO is temporarily unavailable.
        </p>
        <p className="text-[13px]" style={{ color: "var(--kyro-text-muted)" }}>
          {error}
        </p>
        <button
          type="button"
          onClick={() => setAttempt((n) => n + 1)}
          className="rounded-lg px-4 py-2 text-[13px] transition-colors"
          style={{
            background: "var(--kyro-accent)",
            color: "var(--kyro-text)",
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!checked) {
    // Session check in flight (redirects to /login only on a 401).
    return (
      <div
        className="flex h-screen items-center justify-center"
        style={{ background: "var(--kyro-bg)" }}
        aria-busy="true"
        aria-label="Checking session"
      />
    );
  }

  return <AppShell user={user} />;
}
