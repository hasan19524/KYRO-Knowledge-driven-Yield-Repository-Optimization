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
const BACKEND_URL = process.env.KYRO_BACKEND_URL ?? "http://kyro-backend:8000";

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
  const apiKey = process.env.KYRO_API_KEY;
  if (apiKey) headers["X-API-Key"] = apiKey;

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
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ?? "application/json",
      },
    });
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
