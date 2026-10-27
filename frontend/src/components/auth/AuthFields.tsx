"use client";

import { useState, type InputHTMLAttributes, type ReactNode } from "react";
import { CircleAlert, Eye, EyeOff, Lock, type LucideIcon } from "lucide-react";

export function FieldError({ id, message }: { id: string; message: string }) {
  return (
    <p id={id} className="flex items-center gap-1.5 text-[12px] leading-[1.4] text-error">
      <CircleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}

interface AuthInputProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string;
  label: string;
  error?: string;
  icon: LucideIcon;
}

export function AuthInput({ id, label, error, icon: Icon, className, ...input }: AuthInputProps) {
  const errorId = `${id}-error`;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium leading-[1.4] text-text">
        {label}
      </label>
      <div className="relative">
        <Icon
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
          aria-hidden="true"
        />
        <input
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className={`h-12 w-full rounded-lg border bg-card pl-10 pr-3.5 text-[14px] leading-[1.5] text-text transition-colors hover:border-border-hover focus:border-accent-hover ${error ? "border-error" : "border-border"} ${className ?? ""}`}
          {...input}
        />
      </div>
      {error ? <FieldError id={errorId} message={error} /> : null}
    </div>
  );
}

interface PasswordInputProps extends Omit<AuthInputProps, "icon" | "type"> {
  id: string;
  label: string;
  error?: string;
}

export function PasswordInput({ id, label, error, className, ...input }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const errorId = `${id}-error`;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium leading-[1.4] text-text">
        {label}
      </label>
      <div className="relative">
        <Lock
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
          aria-hidden="true"
        />
        <input
          id={id}
          type={visible ? "text" : "password"}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className={`h-12 w-full rounded-lg border bg-card pl-10 pr-12 text-[14px] leading-[1.5] text-text transition-colors hover:border-border-hover focus:border-accent-hover ${error ? "border-error" : "border-border"} ${className ?? ""}`}
          {...input}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute right-1.5 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md text-text-muted transition-colors hover:text-text"
        >
          {visible ? (
            <EyeOff className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Eye className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </div>
      {error ? <FieldError id={errorId} message={error} /> : null}
    </div>
  );
}

interface AuthCheckboxProps {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  children?: ReactNode;
  error?: string;
  disabled?: boolean;
}

export function AuthCheckbox({
  id,
  label,
  checked,
  onChange,
  children,
  error,
  disabled,
}: AuthCheckboxProps) {
  const errorId = `${id}-error`;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-start gap-2.5">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(e) => onChange(e.target.checked)}
          className="mt-[3px] h-4 w-4 shrink-0 cursor-pointer rounded-[4px] border-border accent-[#304d3a] disabled:cursor-not-allowed"
        />
        <div className="text-[13px] leading-[1.5] text-text-secondary">
          <label htmlFor={id} className="cursor-pointer">
            {label}
          </label>
          {children ? <> {children}</> : null}
        </div>
      </div>
      {error ? <FieldError id={errorId} message={error} /> : null}
    </div>
  );
}

export function FormNotice({ children }: { children: ReactNode }) {
  return (
    <p
      role="status"
      aria-live="polite"
      className="flex items-start gap-2.5 rounded-lg border border-border bg-card px-3.5 py-3 text-[13px] leading-[1.5] text-text-secondary"
    >
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-error" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}
