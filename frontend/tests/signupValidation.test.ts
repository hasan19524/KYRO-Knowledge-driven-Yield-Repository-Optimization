import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { validateSignupForm } from "../src/lib/signupValidation.ts";

describe("validateSignupForm", () => {
  it("accepts a matching password with terms accepted", () => {
    const result = validateSignupForm({
      password: "Sup3rSecret-Pw!",
      confirmPassword: "Sup3rSecret-Pw!",
      terms: true,
    });
    assert.equal(result.ok, true);
    assert.equal(result.passwordError, undefined);
    assert.equal(result.termsError, undefined);
  });

  it("rejects mismatched confirm-password and reports it", () => {
    const result = validateSignupForm({
      password: "Sup3rSecret-Pw!",
      confirmPassword: "Sup3rSecret-Pw",
      terms: true,
    });
    assert.equal(result.ok, false);
    assert.equal(result.passwordError, "Passwords do not match.");
    assert.equal(result.termsError, undefined);
  });

  it("rejects unchecked terms and reports it", () => {
    const result = validateSignupForm({
      password: "Sup3rSecret-Pw!",
      confirmPassword: "Sup3rSecret-Pw!",
      terms: false,
    });
    assert.equal(result.ok, false);
    assert.equal(result.passwordError, undefined);
    assert.equal(result.termsError, "Accept the Terms of Service to continue.");
  });

  it("reports both problems at once when they co-occur", () => {
    const result = validateSignupForm({
      password: "one",
      confirmPassword: "two",
      terms: false,
    });
    assert.equal(result.ok, false);
    assert.equal(result.passwordError, "Passwords do not match.");
    assert.equal(result.termsError, "Accept the Terms of Service to continue.");
  });

  it("treats empty confirm-password as a mismatch (not a bypass)", () => {
    const result = validateSignupForm({
      password: "Sup3rSecret-Pw!",
      confirmPassword: "",
      terms: true,
    });
    assert.equal(result.ok, false);
    assert.equal(result.passwordError, "Passwords do not match.");
  });
});
