import { apiFetch } from "@/lib/api/client";
import type { AuthSession, LoginInput, RegisterInput } from "@/types/auth";

export async function register(input: RegisterInput): Promise<AuthSession> {
  return apiFetch<AuthSession>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function login(input: LoginInput): Promise<AuthSession> {
  return apiFetch<AuthSession>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// No logout() — the backend has no session/logout endpoint (stateless JWT). Signing out is
// purely useAuthStore.getState().logout(), called directly from the UI.

export interface TotpSetup {
  secret: string;
  otpauth_url: string;
}

export async function setup2FA(): Promise<TotpSetup> {
  return apiFetch<TotpSetup>("/auth/2fa/setup", { method: "POST" });
}

export async function confirm2FA(code: string): Promise<{ totp_enabled: boolean }> {
  return apiFetch<{ totp_enabled: boolean }>("/auth/2fa/confirm", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export async function disable2FA(code: string): Promise<{ totp_enabled: boolean }> {
  return apiFetch<{ totp_enabled: boolean }>("/auth/2fa/disable", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}
