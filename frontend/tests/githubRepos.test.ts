import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  connectPayload,
  parseRepoOptions,
  repoStatusLabel,
  sortRepoOptions,
} from "../src/lib/githubRepos.ts";
import type { GithubRepoOption } from "../src/lib/githubRepos.ts";

const repo = (overrides: Partial<GithubRepoOption>): GithubRepoOption => ({
  github_repository_id: 1,
  full_name: "hasan/repo",
  name: "repo",
  owner: "hasan",
  private: false,
  default_branch: "main",
  url: null,
  onboarded: false,
  status: null,
  ...overrides,
});

describe("parseRepoOptions", () => {
  it("parses well-formed entries", () => {
    const parsed = parseRepoOptions([
      {
        github_repository_id: 1286911921,
        full_name: "hasan19524/acumen",
        name: "acumen",
        owner: "hasan19524",
        private: false,
        default_branch: "main",
        url: "https://github.com/hasan19524/acumen",
        onboarded: true,
        status: "READY",
      },
    ]);
    assert.ok(parsed);
    assert.equal(parsed.length, 1);
    assert.equal(parsed[0].github_repository_id, 1286911921);
    assert.equal(parsed[0].onboarded, true);
    assert.equal(parsed[0].status, "READY");
  });

  it("skips malformed entries instead of crashing", () => {
    const parsed = parseRepoOptions([
      { github_repository_id: 7, full_name: "a/b", name: "b", owner: "a",
        private: false, default_branch: null, url: null,
        onboarded: false, status: null },
      "not-an-object",
      { github_repository_id: "nope" },
      null,
    ]);
    assert.ok(parsed);
    assert.equal(parsed.length, 1);
    assert.equal(parsed[0].github_repository_id, 7);
  });

  it("fails closed on non-array payloads", () => {
    assert.equal(parseRepoOptions(null), null);
    assert.equal(parseRepoOptions(undefined), null);
    assert.equal(parseRepoOptions({ repositories: [] }), null);
    assert.equal(parseRepoOptions("[]"), null);
  });

  it("fills defaults for missing optional fields", () => {
    const parsed = parseRepoOptions([{ github_repository_id: 42 }]);
    assert.ok(parsed);
    assert.equal(parsed[0].full_name, "repo-42");
    assert.equal(parsed[0].owner, "repo-42");
    assert.equal(parsed[0].private, false);
    assert.equal(parsed[0].default_branch, null);
    assert.equal(parsed[0].onboarded, false);
  });
});

describe("sortRepoOptions", () => {
  it("groups connected repos first, then alphabetical", () => {
    const sorted = sortRepoOptions([
      repo({ github_repository_id: 1, full_name: "hasan/alpha", onboarded: false }),
      repo({ github_repository_id: 2, full_name: "hasan/zed", onboarded: true, status: "READY" }),
      repo({ github_repository_id: 3, full_name: "hasan/beta", onboarded: true, status: "SYNCING" }),
      repo({ github_repository_id: 4, full_name: "hasan/mid", onboarded: false }),
    ]);
    assert.deepEqual(
      sorted.map((r) => r.full_name),
      ["hasan/beta", "hasan/zed", "hasan/alpha", "hasan/mid"]
    );
  });

  it("does not mutate the input array", () => {
    const input = [
      repo({ github_repository_id: 1, full_name: "b" }),
      repo({ github_repository_id: 2, full_name: "a" }),
    ];
    sortRepoOptions(input);
    assert.equal(input[0].full_name, "b");
  });
});

describe("connectPayload", () => {
  it("maps every field the onboard endpoint needs", () => {
    const payload = connectPayload(
      repo({
        github_repository_id: 1395956448,
        full_name: "hasan19524/KYRO-ingestion-test",
        name: "KYRO-ingestion-test",
        owner: "hasan19524",
        private: true,
        default_branch: "master",
        url: "https://github.com/hasan19524/KYRO-ingestion-test",
      })
    );
    assert.deepEqual(payload, {
      github_repository_id: 1395956448,
      owner: "hasan19524",
      name: "KYRO-ingestion-test",
      full_name: "hasan19524/KYRO-ingestion-test",
      default_branch: "master",
      private: true,
      url: "https://github.com/hasan19524/KYRO-ingestion-test",
    });
  });

  it("omits absent optional fields from the wire payload", () => {
    const payload = connectPayload(repo({ default_branch: null, url: null }));
    // The contract is the JSON body the backend receives; JSON.stringify
    // drops undefined-valued keys, so they never reach the wire.
    const wire: Record<string, unknown> = JSON.parse(JSON.stringify(payload));
    assert.equal("default_branch" in wire, false);
    assert.equal("url" in wire, false);
  });
});

describe("repoStatusLabel", () => {
  it("maps the known KYRO statuses", () => {
    assert.equal(repoStatusLabel("READY"), "Connected");
    assert.equal(repoStatusLabel("SYNCING"), "Indexing…");
    assert.equal(repoStatusLabel("SYNC_FAILED"), "Sync failed");
    assert.equal(repoStatusLabel("ACCESS_REVOKED"), "Access revoked");
  });

  it("passes through unknown statuses and defaults null", () => {
    assert.equal(repoStatusLabel("SOMETHING_NEW"), "SOMETHING_NEW");
    assert.equal(repoStatusLabel(null), "Connected");
  });
});
