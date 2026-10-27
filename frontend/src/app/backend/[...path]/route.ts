import { NextRequest, NextResponse } from "next/server";

import { isAllowedOrigin, isAllowedPath, selfOriginFromHeaders } from "../proxyPolicy";

// Server-side only: KYRO_BACKEND_URL / KYRO_API_KEY are never exposed to the
// browser (no NEXT_PUBLIC_ prefix). The API key is injected here so all
// forwarding requests reach the backend authenticated.
//
// SECURITY: only allowlisted backend paths are forwarded (anything else —
// especially the admin /api/users surface — gets 403), and state-changing
// POSTs must come from this same origin (CSRF guard). The shared key stays
// server-side and is never returned to the browser.
//
// Login sessions: the httpOnly `kyro_session` cookie set by this route is
// forwarded to the backend as `Authorization: Bearer ...`; register/login
// responses move the token from the JSON body into the cookie (the browser
// JS never sees it), and logout clears it. A present cookie takes precedence
// over the injected service key at the backend, so a bad/expired session is
// a terminal 401 rather than a fallback to the shared-key identity.
// Default targets the HOST-run backend (native `next dev`); container runs
// always override via app/docker-compose.yml `environment:` (service DNS),
// so the default only ever applies natively — see frontend/.env.local.
const BACKEND_URL = process.env.KYRO_BACKEND_URL ?? "http://127.0.0.1:8000";

const SESSION_COOKIE = "kyro_session";
// Matches the backend default AUTH_SESSION_TTL_HOURS (168h = 7 days).
const SESSION_MAX_AGE_S = 7 * 24 * 60 * 60;
// Secure cookies default on in production; local http:// deployments can
// opt out with KYRO_COOKIE_SECURE=0 (browsers reject Secure cookies on
// plain-http origins other than localhost).
const COOKIE_SECURE =
  process.env.NODE_ENV === "production" &&
  process.env.KYRO_COOKIE_SECURE !== "0";

function sessionCookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: COOKIE_SECURE,
    path: "/",
    maxAge,
  };
}

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function forward(
  request: NextRequest,
  context: RouteContext,
  method: "GET" | "POST"
): Promise<NextResponse> {
  const { path } = await context.params;
  if (!path || path.length === 0) {
    return NextResponse.json({ error: "missing backend path" }, { status: 404 });
  }

  if (!isAllowedPath(path)) {
    return NextResponse.json(
      { error: "path not allowed through the frontend proxy" },
      { status: 403 }
    );
  }

  if (
    !isAllowedOrigin(
      method,
      request.headers.get("origin"),
      request.headers.get("referer"),
      selfOriginFromHeaders(request.headers)
    )
  ) {
    return NextResponse.json(
      { error: "cross-origin state-changing request rejected" },
      { status: 403 }
    );
  }

  // Percent-encode each segment so a crafted path can never traverse out of
  // the backend's route space (defense in depth on top of the allowlist).
  const target = `${BACKEND_URL}/${path
    .map((segment) => encodeURIComponent(segment))
    .join("/")}${request.nextUrl.search}`;
  const headers: Record<string, string> = {};
  const contentType = request.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;
  const sessionToken = request.cookies.get(SESSION_COOKIE)?.value;
  if (sessionToken) headers["Authorization"] = `Bearer ${sessionToken}`;
  const apiKey = process.env.KYRO_API_KEY;
  if (apiKey) headers["X-API-Key"] = apiKey;

  // GitHub OAuth redirect flow: these GETs are browser navigations where the
  // backend answers 302s (to GitHub on /start, back to /app on /callback).
  // The proxy forwards the redirect + the backend's session Set-Cookie
  // verbatim, and tells the backend which public origin the browser used so
  // its redirect_uri matches the URL registered at the GitHub App exactly.
  const isGithubOauth =
    path[0] === "api" &&
    path[1] === "auth" &&
    path[2] === "github" &&
    (path[3] === "start" || path[3] === "callback");
  if (isGithubOauth) {
    headers["X-Kyro-Self-Origin"] = selfOriginFromHeaders(request.headers);
  }

  let body: string | undefined;
  if (method === "POST") {
    body = await request.text();
    if (!body) body = undefined;
  }

  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      // manual: the browser (not this server) must follow the 302 to GitHub.
      redirect: isGithubOauth ? "manual" : "follow",
    });

    if (isGithubOauth && upstream.status >= 300 && upstream.status < 400) {
      const response = new NextResponse(null, { status: upstream.status });
      const location = upstream.headers.get("location");
      if (location) response.headers.set("Location", location);
      // e.g. kyro_session set by the backend on a successful callback.
      for (const cookie of upstream.headers.getSetCookie()) {
        response.headers.append("set-cookie", cookie);
      }
      return response;
    }
    // Non-3xx on an OAuth route (e.g. 503 unconfigured, 429 rate limited)
    // carries a JSON error body — forwarded by the normal path below.

    const text = await upstream.text();

    const isAuthRoute = path[0] === "api" && path[1] === "auth";
    const responseHeaders: Record<string, string> = {
      "Content-Type":
        upstream.headers.get("content-type") ?? "application/json",
    };
    // 204/205/304 are null-body statuses: the Response constructor throws
    // if any body (even "") is attached, so pass null explicitly.
    const nullBody =
      upstream.status === 204 || upstream.status === 205 || upstream.status === 304;

    if (isAuthRoute && (path[2] === "register" || path[2] === "login")) {
      // Move the session token out of the response body into the httpOnly
      // cookie: browser JS gets the identity, never the secret.
      try {
        const data = JSON.parse(text) as Record<string, unknown>;
        const token = data["token"];
        if (upstream.ok && typeof token === "string") {
          delete data["token"];
          const response = new NextResponse(JSON.stringify(data), {
            status: upstream.status,
            headers: responseHeaders,
          });
          response.cookies.set(
            SESSION_COOKIE,
            token,
            sessionCookieOptions(SESSION_MAX_AGE_S)
          );
          return response;
        }
      } catch {
        // Non-JSON body (error passthrough) — fall through below.
      }
    }

    const response = new NextResponse(nullBody ? null : text, {
      status: upstream.status,
      headers: nullBody ? undefined : responseHeaders,
    });
    if (isAuthRoute && path[2] === "logout") {
      // Clear unconditionally: even a 401 from an already-expired session
      // should not leave a stale cookie behind.
      response.cookies.set(SESSION_COOKIE, "", sessionCookieOptions(0));
    }
    return response;
  } catch {
    return NextResponse.json(
      { detail: "KYRO backend is unreachable" },
      { status: 502 }
    );
  }
}

export async function GET(request: NextRequest, context: RouteContext) {
  return forward(request, context, "GET");
}

export async function POST(request: NextRequest, context: RouteContext) {
  return forward(request, context, "POST");
}
