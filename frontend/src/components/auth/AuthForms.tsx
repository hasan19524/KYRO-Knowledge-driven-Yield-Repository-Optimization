"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Mail, User } from "lucide-react";
import { submitAuth, type AuthResult } from "@/lib/auth";
import { validateSignupForm } from "@/lib/signupValidation";
import { AuthCheckbox, AuthInput, FormNotice, PasswordInput } from "./AuthFields";
import { AuthDivider, AuthSwitchLink, GithubSignInButton, PrimaryButton } from "./AuthControls";

const APP_ROUTE = "/app";

interface LoginFormProps {
  /** True when the OAuth callback bounced here with ?error=github. */
  githubError?: boolean;
}

export function LoginForm({ githubError = false }: LoginFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [notice, setNotice] = useState<string | null>(
    githubError ? "GitHub sign-in didn't complete. Please try again." : null
  );
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Strip ?error=github after the first render so a refresh doesn't
    // replay the stale error (external-system update only, no setState).
    if (githubError && typeof window !== "undefined") {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [githubError]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setLoading(true);
    const result: AuthResult = await submitAuth({ mode: "login", email, password });
    if (result.ok) {
      router.replace(APP_ROUTE);
    } else {
      setLoading(false);
      setNotice(result.message);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="kyro-overline" style={{ color: "var(--kyro-accent-hover)" }}>
          Welcome back
        </p>
        <h1 className="text-[24px] font-semibold leading-[1.2] tracking-[-0.02em] text-text sm:text-[28px]">
          Sign in to KYRO
        </h1>
        <p className="text-[14px] leading-[1.6] text-text-secondary">
          Enter your credentials to continue to your workspace.
        </p>
      </header>

      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
        {notice ? <FormNotice>{notice}</FormNotice> : null}

        <div className="flex flex-col gap-4">
          <AuthInput
            id="email"
            label="Email"
            type="email"
            icon={Mail}
            placeholder="you@company.com"
            value={email}
            disabled={loading}
            autoComplete="email"
            spellCheck={false}
            className="disabled:cursor-not-allowed disabled:opacity-60"
            onChange={(e) => setEmail(e.target.value)}
          />
          <PasswordInput
            id="password"
            label="Password"
            placeholder="Enter your password"
            value={password}
            disabled={loading}
            autoComplete="current-password"
            className="disabled:cursor-not-allowed disabled:opacity-60"
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <AuthCheckbox
          id="remember"
          label="Remember me"
          checked={remember}
          disabled={loading}
          onChange={setRemember}
        />

        <PrimaryButton loading={loading} loadingLabel="Signing in">
          Sign in
        </PrimaryButton>
      </form>

      <div className="flex flex-col gap-4">
        <AuthDivider />
        <GithubSignInButton />
      </div>

      <AuthSwitchLink
        prompt="Don't have an account?"
        href="/"
        action="Create one"
      />
    </div>
  );
}

export function SignupForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [terms, setTerms] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [termsError, setTermsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);

    const validation = validateSignupForm({ password, confirmPassword, terms });
    setConfirmError(validation.passwordError ?? null);
    setTermsError(validation.termsError ?? null);
    if (!validation.ok) {
      // Local validation failed — do not call the backend or set loading.
      return;
    }

    setLoading(true);
    const result: AuthResult = await submitAuth({
      mode: "signup",
      name,
      email,
      password,
    });
    if (result.ok) {
      router.replace(APP_ROUTE);
    } else {
      setLoading(false);
      setNotice(result.message);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="kyro-overline" style={{ color: "var(--kyro-accent-hover)" }}>
          Create your workspace
        </p>
        <h1 className="text-[24px] font-semibold leading-[1.2] tracking-[-0.02em] text-text sm:text-[28px]">
          Create your account
        </h1>
        <p className="text-[14px] leading-[1.6] text-text-secondary">
          Set up your KYRO workspace and connect a repository in minutes.
        </p>
      </header>

      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
        {notice ? <FormNotice>{notice}</FormNotice> : null}

        <div className="flex flex-col gap-4">
          <AuthInput
            id="name"
            label="Full name"
            type="text"
            icon={User}
            placeholder="Ada Lovelace"
            value={name}
            disabled={loading}
            autoComplete="name"
            className="disabled:cursor-not-allowed disabled:opacity-60"
            onChange={(e) => setName(e.target.value)}
          />
          <AuthInput
            id="email"
            label="Email"
            type="email"
            icon={Mail}
            placeholder="you@company.com"
            value={email}
            disabled={loading}
            autoComplete="email"
            spellCheck={false}
            className="disabled:cursor-not-allowed disabled:opacity-60"
            onChange={(e) => setEmail(e.target.value)}
          />
          <PasswordInput
            id="password"
            label="Password"
            placeholder="At least 8 characters"
            value={password}
            disabled={loading}
            autoComplete="new-password"
            className="disabled:cursor-not-allowed disabled:opacity-60"
            onChange={(e) => {
              setPassword(e.target.value);
              if (confirmError) setConfirmError(null);
            }}
          />
          <PasswordInput
            id="confirmPassword"
            label="Confirm password"
            placeholder="Repeat your password"
            value={confirmPassword}
            disabled={loading}
            autoComplete="new-password"
            error={confirmError ?? undefined}
            className="disabled:cursor-not-allowed disabled:opacity-60"
            onChange={(e) => {
              setConfirmPassword(e.target.value);
              if (confirmError) setConfirmError(null);
            }}
          />
        </div>

        <AuthCheckbox
          id="terms"
          label="I agree to the Terms of Service and Privacy Policy"
          checked={terms}
          disabled={loading}
          error={termsError ?? undefined}
          onChange={(checked) => {
            setTerms(checked);
            if (checked && termsError) setTermsError(null);
          }}
        />

        <PrimaryButton loading={loading} loadingLabel="Creating account">
          Create account
        </PrimaryButton>
      </form>

      <div className="flex flex-col gap-4">
        <AuthDivider />
        <GithubSignInButton />
      </div>

      <AuthSwitchLink
        prompt="Already have an account?"
        href="/login"
        action="Sign in"
      />
    </div>
  );
}
