import type { NextRequest } from "next/server";

// First-party health endpoint (survival/liveness checks). Historical context:
// while the frontend served :3000, an external prober polled
// http://127.0.0.1:3000/health roughly once a minute and terminated whatever
// held that port - even when this answered 200 (observed 2026-10-19: four
// consecutive dev-server deaths, each with `GET /health` as the final log
// line before teardown). The frontend now serves :3001 (package.json dev
// script / Stack B host mapping) where nothing probes it. Kept so any future
// prober can be named from the dev log via the identity line below.
// (Proxied backend health stays /backend/health -> allowlist -> backend /health.)
export async function GET(request: NextRequest) {
  const h = request.headers;
  console.log(
    `[health-probe] ${new Date().toISOString()} ${request.method} ` +
      `${request.nextUrl.pathname} ua=${h.get("user-agent")} ` +
      `accept=${h.get("accept")} from=${h.get("from")} ` +
      `xff=${h.get("x-forwarded-for")}`
  );
  return Response.json({ status: "ok", service: "kyro-frontend" });
}
