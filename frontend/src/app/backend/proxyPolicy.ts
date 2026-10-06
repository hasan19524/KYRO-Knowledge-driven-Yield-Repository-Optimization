// Pure policy helpers for the /backend/[...path] proxy — kept free of Next.js
// imports so they can be unit-tested with the Node test runner (`npm test`).

/** Only these backend paths may be reached through the frontend proxy. */
const NUMERIC = /^\d+$/;

export function isAllowedPath(segments: string[]): boolean {
  if (segments.length === 0) return false;
  if (segments.length === 1) return segments[0] === "health";
  if (segments[0] !== "api") return false;
  if (segments[1] === "query") return segments.length === 2;
  if (segments[1] === "repositories") {
    if (segments.length === 2) return true;
    if (segments.length === 3) {
      return NUMERIC.test(segments[2]) || segments[2] === "onboard";
    }
    if (segments.length === 4) {
      return NUMERIC.test(segments[2]) && segments[3] === "resync";
    }
  }
  // Everything else — notably /api/users (admin) and /docs — is rejected.
  return false;
}

/**
 * The origin this request was actually targeted at, derived from the Host
 * header (plus optional proxy protocol). `nextUrl.origin` is UNSAFE here:
 * the standalone server reports its bind address (0.0.0.0), not the Host
 * the browser used, so same-origin comparisons against it always fail.
 */
export function selfOriginFromHeaders(headers: {
  get(name: string): string | null;
}): string {
  const host = headers.get("host");
  if (!host) return "";
  const proto = (headers.get("x-forwarded-proto") ?? "http")
    .split(",")[0]
    .trim();
  return `${proto}://${host}`;
}

/**
 * CSRF guard for state-changing proxied requests.
 *
 * Browser cross-origin POSTs always carry an Origin header (or a Referer
 * fallback); a mismatch with the proxy's own origin is rejected. Header-less
 * requests (curl, server-to-server) carry no browser context and are allowed.
 * GET never changes state and is not gated.
 */
export function isAllowedOrigin(
  method: string,
  origin: string | null,
  referer: string | null,
  selfOrigin: string
): boolean {
  if (method !== "POST") return true;

  let candidate: string | null = null;
  if (origin !== null && origin !== "") {
    candidate = origin;
  } else if (referer !== null && referer !== "") {
    try {
      candidate = new URL(referer).origin;
    } catch {
      return false;
    }
  }

  if (candidate === null) return true; // no browser context headers
  if (candidate === "null") return false; // opaque origin (sandboxed frame)
  if (selfOrigin === "") return false; // cannot establish own origin -> fail closed
  return candidate === selfOrigin;
}
