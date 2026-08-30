import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { AuthSession, Tenant, User } from "@/types/auth";

interface AuthState {
  user: User | null;
  tenant: Tenant | null;
  accessToken: string | null;
  /** Convenience only — prefilled into the login form, not a real "find my org" lookup. */
  lastTenantSlug: string | null;
  hasHydrated: boolean;
  isAuthenticated: () => boolean;
  setSession: (session: AuthSession) => void;
  logout: () => void;
  setHasHydrated: (hydrated: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      tenant: null,
      accessToken: null,
      lastTenantSlug: null,
      hasHydrated: false,
      isAuthenticated: () => get().accessToken !== null,
      setSession: (session) =>
        set({
          user: session.user,
          tenant: session.tenant,
          accessToken: session.access_token,
          lastTenantSlug: session.tenant.slug,
        }),
      logout: () => set({ user: null, tenant: null, accessToken: null }),
      setHasHydrated: (hydrated) => set({ hasHydrated: hydrated }),
    }),
    {
      name: "krixil-auth",
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
      partialize: (state) => ({
        user: state.user,
        tenant: state.tenant,
        accessToken: state.accessToken,
        lastTenantSlug: state.lastTenantSlug,
      }),
    },
  ),
);
