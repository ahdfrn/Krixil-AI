export interface User {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  totp_enabled: boolean;
  memory_enabled: boolean;
  created_at: string;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
}

/** Matches the backend's TokenResponse exactly (POST /auth/register and /auth/login). */
export interface AuthSession {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  tenant: Tenant;
}

export interface RegisterInput {
  tenant_name: string;
  email: string;
  password: string;
}

export interface LoginInput {
  tenant_slug: string;
  email: string;
  password: string;
  totp_code?: string;
}
