import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  isAllowedOrigin,
  isAllowedPath,
  selfOriginFromHeaders,
} from "../src/app/backend/proxyPolicy.ts";

function headers(map: Record<string, string>) {
  return {
    get(name: string): string | null {
      return map[name.toLowerCase()] ?? null;
    },
  };
}

describe("proxy path allowlist", () => {
  it("allows the paths the frontend legitimately needs", () => {
    assert.equal(isAllowedPath(["health"]), true);
    assert.equal(isAllowedPath(["api", "query"]), true);
    assert.equal(isAllowedPath(["api", "repositories"]), true);
    assert.equal(isAllowedPath(["api", "repositories", "900001"]), true);
    assert.equal(isAllowedPath(["api", "repositories", "onboard"]), true);
    assert.equal(isAllowedPath(["api", "repositories", "900001", "resync"]), true);
  });

  it("rejects admin and unrelated backend paths", () => {
    assert.equal(isAllowedPath(["api", "users"]), false);
    assert.equal(isAllowedPath(["api", "users", "2"]), false);
    assert.equal(isAllowedPath(["api", "users", "2", "rotate-key"]), false);
    assert.equal(isAllowedPath(["api", "users", "2", "deactivate"]), false);
    assert.equal(isAllowedPath(["docs"]), false);
    assert.equal(isAllowedPath(["redoc"]), false);
    assert.equal(isAllowedPath(["openapi.json"]), false);
    assert.equal(isAllowedPath(["api"]), false);
    assert.equal(isAllowedPath([]), false);
  });

  it("rejects malformed repository paths", () => {
    assert.equal(isAllowedPath(["api", "repositories", "abc"]), false);
    assert.equal(isAllowedPath(["api", "repositories", "1", "other"]), false);
    assert.equal(isAllowedPath(["api", "repositories", "1", "resync", "x"]), false);
    assert.equal(isAllowedPath(["api", "query", "extra"]), false);
    assert.equal(isAllowedPath(["other", "thing"]), false);
  });
});

describe("proxy origin (CSRF) guard", () => {
  const self = "http://localhost:3000";

  it("allows same-origin state-changing requests", () => {
    assert.equal(isAllowedOrigin("POST", self, null, self), true);
    assert.equal(
      isAllowedOrigin("POST", null, "http://localhost:3000/chat", self),
      true
    );
  });

  it("rejects cross-origin state-changing requests", () => {
    assert.equal(isAllowedOrigin("POST", "https://evil.example", null, self), false);
    assert.equal(
      isAllowedOrigin("POST", null, "https://evil.example/x", self),
      false
    );
    assert.equal(isAllowedOrigin("POST", "null", null, self), false);
    assert.equal(isAllowedOrigin("POST", null, "not-a-url", self), false);
  });

  it("allows header-less (non-browser) requests and all GETs", () => {
    assert.equal(isAllowedOrigin("POST", null, null, self), true);
    assert.equal(isAllowedOrigin("GET", "https://evil.example", null, self), true);
    assert.equal(isAllowedOrigin("GET", null, "https://evil.example/x", self), true);
  });

  it("fails closed when the request's own origin cannot be established", () => {
    assert.equal(isAllowedOrigin("POST", self, null, ""), false);
    assert.equal(isAllowedOrigin("POST", null, null, ""), true);
  });
});

describe("self origin from headers", () => {
  it("uses the Host header and defaults to http", () => {
    assert.equal(
      selfOriginFromHeaders(headers({ host: "localhost:3000" })),
      "http://localhost:3000"
    );
  });

  it("honours x-forwarded-proto behind a TLS proxy", () => {
    assert.equal(
      selfOriginFromHeaders(
        headers({
          host: "kyro.example",
          "x-forwarded-proto": "https",
        })
      ),
      "https://kyro.example"
    );
  });

  it("returns empty string without a host header", () => {
    assert.equal(selfOriginFromHeaders(headers({})), "");
  });
});
