/**
 * Client-side account auth (additive login system).
 *
 * All calls go through the Next.js backend proxy (/backend/api/auth/*),
 * which stores the session token in an httpOnly `kyro_session` cookie and
 * forwards it to the backend as `Authorization: Bearer`. The browser never
 * sees, stores, or forwards the token itself — only the cookie exists, and
 * it is set/cleared server-side by the proxy route.
 */

export type AuthMode = "login" | "signup";

export interface AuthPayload {
  mode: AuthMode;
  name?: string;
  email: string;
  password: string;
}

export type AuthResult = { ok: true } | { ok: false; message: string };

export interface AuthUser {
  id: number;
  handle: string;
  email: string | null;
  /** Set when the account was created/linked via "Sign in with GitHub". */
  github_login?: string | null;
}

function messageFromDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // pydantic validation errors: [{ msg, loc, ... }]
    const first: unknown = detail[0];
    if (first && typeof first === "object" && "msg" in first) {
      return String((first as { msg: unknown }).msg);
    }
    return null;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message: unknown }).message;
    if (typeof message === "string") return message;
  }
  return null;
}

async function postAuth(path: string, body: unknown): Promise<AuthResult> {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) return { ok: true };
    const data: unknown = await res.json().catch(() => null);
    const detail = (data as { detail?: unknown } | null)?.detail;
    return {
      ok: false,
      message: messageFromDetail(detail) ?? `Request failed (HTTP ${res.status})`,
    };
  } catch {
    return { ok: false, message: "KYRO backend is unreachable. Is it running?" };
  }
}

export function submitAuth(payload: AuthPayload): Promise<AuthResult> {
  const base = { email: payload.email, password: payload.password };
  if (payload.mode === "signup") {
    return postAuth("/backend/api/auth/register", {
      ...base,
      ...(payload.name ? { name: payload.name } : {}),
    });
  }
  return postAuth("/backend/api/auth/login", base);
}

/**
 * Result of a session check — three distinct outcomes so a backend outage is
 * never mistaken for a logged-out session (an outage must NOT bounce the user
 * to the login page; only a real 401 may do that).
 */
export type SessionCheck =
  | { state: "authenticated"; user: AuthUser }
  | { state: "unauthenticated" } // 401: session invalid or expired
  | { state: "error"; message: string }; // 5xx / network: backend unavailable

export async function checkSession(): Promise<SessionCheck> {
  let res: Response;
  try {
    res = await fetch("/backend/api/auth/me", { cache: "no-store" });
  } catch {
    return { state: "error", message: "KYRO backend is unreachable. Is it running?" };
  }
  if (res.status === 401) return { state: "unauthenticated" };
  if (!res.ok) {
    return { state: "error", message: `Backend unavailable (HTTP ${res.status})` };
  }
  try {
    return { state: "authenticated", user: (await res.json()) as AuthUser };
  } catch {
    return { state: "error", message: "Backend returned an unreadable response." };
  }
}

/**
 * True only when a response means "the session is invalid or expired".
 * 5xx and network failures are NOT authentication failures and must never
 * trigger a logout/redirect loop.
 */
export function isSessionExpired(res: Response): boolean {
  return res.status === 401;
}

/** Server-side session invalidation; the proxy also clears the cookie. */
export async function logout(): Promise<void> {
  try {
    await fetch("/backend/api/auth/logout", { method: "POST" });
  } catch {
    // Backend unreachable — the session still expires server-side.
  }
}
