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
