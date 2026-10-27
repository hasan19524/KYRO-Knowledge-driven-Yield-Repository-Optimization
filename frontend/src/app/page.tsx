import type { Metadata } from "next";
import AuthLayout from "@/components/auth/AuthLayout";
import { SignupForm } from "@/components/auth/AuthForms";

export const metadata: Metadata = {
  title: "Create account — KYRO",
  description:
    "Create a KYRO workspace and get answers grounded in your repository.",
};

export default function SignupPage() {
  return (
    <AuthLayout mode="signup">
      <SignupForm />
    </AuthLayout>
  );
}
