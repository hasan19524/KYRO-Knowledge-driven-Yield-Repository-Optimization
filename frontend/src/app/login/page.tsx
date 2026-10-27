import type { Metadata } from "next";
import AuthLayout from "@/components/auth/AuthLayout";
import { LoginForm } from "@/components/auth/AuthForms";

export const metadata: Metadata = {
  title: "Sign in — KYRO",
  description:
    "Sign in to KYRO to ask questions about your code, commits, and architecture.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  // The GitHub OAuth callback redirects here on failure (?error=github);
  // read it server-side so the banner renders in the initial HTML.
  const { error } = await searchParams;
  return (
    <AuthLayout mode="login">
      <LoginForm githubError={error === "github"} />
    </AuthLayout>
  );
}
