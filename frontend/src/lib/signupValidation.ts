/**
 * Client-side signup validation (confirm-password match + terms acceptance).
 *
 * Pure and framework-free so it is unit-testable. The backend enforces its
 * own password/email rules; this only prevents obviously-incomplete signups
 * (mismatched confirmation, unchecked terms) from reaching the network.
 */

export interface SignupInput {
  password: string;
  confirmPassword: string;
  terms: boolean;
}

export interface SignupValidation {
  ok: boolean;
  passwordError?: string;
  termsError?: string;
}

export function validateSignupForm(input: SignupInput): SignupValidation {
  const result: SignupValidation = { ok: true };
  if (input.password !== input.confirmPassword) {
    result.ok = false;
    result.passwordError = "Passwords do not match.";
  }
  if (!input.terms) {
    result.ok = false;
    result.termsError = "Accept the Terms of Service to continue.";
  }
  return result;
}
