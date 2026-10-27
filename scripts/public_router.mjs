// Single public entrypoint for the quick tunnel (one URL for UI + webhook).
//
//   browser/gh -> cloudflared -> 127.0.0.1:8090 (this router)
//     /webhook/*  -> 127.0.0.1:5678  (n8n production webhooks; path preserved
//                                      so /webhook/github arrives as-is)
//     everything else -> 127.0.0.1:3001 (Next.js frontend, which itself
//                                      proxies /backend/* to the API)
//
// Security posture: loopback-only bind; :8000 (API), :5433 (Postgres),
// :8100 (Chroma), :9092 (Kafka) and the n8n editor UI are never routed.
// The original Host header is preserved end-to-end so the frontend proxy's
// same-origin/CSRF check (selfOrigin = x-forwarded-proto://Host) sees the
// public hostname, and x-forwarded-proto is injected only if absent.

import http from "node:http";
import net from "node:net";

const ROUTER = { host: "127.0.0.1", port: 8090 };
const N8N = { host: "127.0.0.1", port: 5678 };
const FRONTEND = { host: "127.0.0.1", port: 3001 };

const server = http.createServer((req, res) => {
  const path = req.url ?? "/";
  const target = path.startsWith("/webhook/") ? N8N : FRONTEND;

  const headers = { ...req.headers };
  if (!headers["x-forwarded-proto"]) headers["x-forwarded-proto"] = "https";

  const upstream = http.request(
    {
      host: target.host,
      port: target.port,
      method: req.method,
      path,
      headers, // Host stays the public hostname on purpose (same-origin checks)
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode ?? 502, upstreamRes.headers);
      upstreamRes.pipe(res);
    }
  );

  upstream.on("error", (err) => {
    if (!res.headersSent) {
      res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    }
    res.end(`upstream unavailable (${target.port}): ${err.code ?? err.message}`);
  });

  req.pipe(upstream);
});

server.on("error", (err) => {
  // Exit non-zero so a duplicate start is visible; the already-running
  // instance keeps serving (startup.md skips when the port is taken).
  console.error(`[router] ${err.message}`);
  process.exit(1);
});

// WebSocket upgrade forwarding. The Next.js dev client only finishes
// hydrating the page after its HMR socket connects, so without this the
// public UI would load but stay frozen. Only the HMR path is replayed
// (verbatim, Host preserved so allowedDevOrigins sees the public hostname);
// any other upgrade request is refused. No-op against a production frontend
// (no /_next/hmr there — the socket simply fails and the page still boots).
server.on("upgrade", (req, socket, head) => {
  const path = req.url ?? "/";
  if (!path.startsWith("/_next/hmr")) {
    socket.destroy();
    return;
  }
  const upstream = net.connect(FRONTEND.port, FRONTEND.host, () => {
    let raw = `${req.method} ${req.url} HTTP/1.1\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      raw += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
    }
    // Exactly ONE blank line ends the headers. An extra CRLF would arrive as
    // stray upgrade-payload bytes, which Next's HMR server treats as a tainted
    // connection: it answers the handshake, sends two frames, then FINs — and
    // the page stays frozen because hydration waits on this socket.
    upstream.write(`${raw}\r\n`);
    if (head && head.length) upstream.write(head);
    socket.pipe(upstream);
    upstream.pipe(socket);
  });
  upstream.on("error", () => socket.destroy());
  socket.on("error", () => upstream.destroy());
  upstream.on("close", () => socket.destroy());
  socket.on("close", () => upstream.destroy());
});

server.listen(ROUTER.port, ROUTER.host, () => {
  console.log(
    `[router] http://127.0.0.1:${ROUTER.port}  /webhook/* -> :${N8N.port},  /* -> :${FRONTEND.port}`
  );
});
