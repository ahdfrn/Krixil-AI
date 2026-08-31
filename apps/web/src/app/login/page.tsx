"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { login } from "@/lib/api/auth";
import { useAuthStore } from "@/stores/auth-store";

export default function LoginPage() {
  const router = useRouter();
  const hasHydrated = useAuthStore((s) => s.hasHydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());
  const lastTenantSlug = useAuthStore((s) => s.lastTenantSlug);
  const setSession = useAuthStore((s) => s.setSession);

  // null = the user hasn't typed in this field yet, so it falls back to the remembered slug from
  // a prior session (once hydration resolves it) — typing anything switches it to user-controlled.
  const [tenantSlugInput, setTenantSlugInput] = useState<string | null>(null);
  const tenantSlug = tenantSlugInput ?? lastTenantSlug ?? "";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [totpCode, setTotpCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (hasHydrated && isAuthenticated) router.replace("/chat");
  }, [hasHydrated, isAuthenticated, router]);

  if (!hasHydrated || isAuthenticated) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const session = await login({
        tenant_slug: tenantSlug.trim(),
        email: email.trim(),
        password,
        ...(needsTotp ? { totp_code: totpCode.trim() } : {}),
      });
      setSession(session);
      router.replace("/chat");
    } catch (err) {
      if (err instanceof ApiError && err.message === "2FA code required") {
        // Not a failure — the password was correct, this account just has 2FA on. Reveal the
        // code field instead of showing an error.
        setNeedsTotp(true);
      } else {
        toast.error(err instanceof ApiError ? err.message : "Couldn't reach Krixil AI — check your connection.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      description="Log in to your Krixil AI workspace."
      footer={
        <>
          Don&apos;t have a workspace?{" "}
          <Link href="/register" className="text-foreground underline underline-offset-2">
            Create one
          </Link>
        </>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tenant_slug">Workspace slug</Label>
          <Input
            id="tenant_slug"
            value={tenantSlug}
            onChange={(e) => setTenantSlugInput(e.target.value)}
            placeholder="acme-corp-a1b2c3"
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            disabled={needsTotp}
            required
          />
        </div>
        {needsTotp && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="totp_code">Authenticator code</Label>
            <Input
              id="totp_code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              placeholder="123456"
              maxLength={6}
              autoFocus
              required
            />
            <p className="text-xs text-muted-foreground">
              This workspace has two-factor authentication on. Enter the 6-digit code from your
              authenticator app.
            </p>
          </div>
        )}
        <Button type="submit" disabled={isSubmitting} className="mt-1 w-full">
          {isSubmitting ? "Logging in..." : needsTotp ? "Verify code" : "Log in"}
        </Button>
      </form>
    </AuthShell>
  );
}
