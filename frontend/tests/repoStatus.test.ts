import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  composerPlaceholder,
  formatElapsed,
  isRepositoryBlocked,
  truncateError,
} from "../src/lib/repoStatus.ts";

describe("isRepositoryBlocked", () => {
  it("blocks the three non-queryable statuses", () => {
    assert.equal(isRepositoryBlocked("SYNCING"), true);
    assert.equal(isRepositoryBlocked("SYNC_FAILED"), true);
    assert.equal(isRepositoryBlocked("ACCESS_REVOKED"), true);
  });

  it("allows READY and unknown/absent statuses", () => {
    assert.equal(isRepositoryBlocked("READY"), false);
    assert.equal(isRepositoryBlocked(null), false);
    assert.equal(isRepositoryBlocked(undefined), false);
    assert.equal(isRepositoryBlocked("SOMETHING_NEW"), false);
  });
});

describe("formatElapsed", () => {
  it("renders m:ss with a zero-padded seconds part", () => {
    assert.equal(formatElapsed(0), "0:00");
    assert.equal(formatElapsed(59), "0:59");
    assert.equal(formatElapsed(60), "1:00");
    assert.equal(formatElapsed(131), "2:11");
    assert.equal(formatElapsed(1312), "21:52");
  });

  it("floors negatives and fractional seconds", () => {
    assert.equal(formatElapsed(-5), "0:00");
    assert.equal(formatElapsed(61.9), "1:01");
  });
});

describe("composerPlaceholder", () => {
  it("names the repository while it is indexing", () => {
    assert.match(
      composerPlaceholder("SYNCING", "hasan19524/Nexus"),
      /hasan19524\/Nexus/
    );
    assert.match(composerPlaceholder("SYNCING", null), /this repository/);
  });

  it("explains failure and revoked access", () => {
    assert.match(composerPlaceholder("SYNC_FAILED", null), /re-sync/i);
    assert.match(composerPlaceholder("ACCESS_REVOKED", null), /re-authorize/i);
  });
});

describe("truncateError", () => {
  it("collapses whitespace and bounds length", () => {
    assert.equal(truncateError("  a\n  b  "), "a b");
    assert.equal(truncateError(null), "");
    assert.equal(truncateError(undefined), "");
    assert.equal(truncateError("x".repeat(300)).length, 200);
    assert.equal(truncateError("short", 200), "short");
  });
});
