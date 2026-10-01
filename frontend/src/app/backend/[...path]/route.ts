import { NextRequest, NextResponse } from "next/server";

// Server-side only: KYRO_BACKEND_URL / KYRO_API_KEY are never exposed to the
// browser (no NEXT_PUBLIC_ prefix). The API key is injected here so all
// mutation/query requests reach the backend authenticated.
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

  const target = `${BACKEND_URL}/${path.join("/")}${request.nextUrl.search}`;
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
