import { useAuthStore } from "@/stores/auth-store";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function extractDetail(body: unknown): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e) => (typeof e === "object" && e !== null && "msg" in e ? String(e.msg) : String(e)))
        .join("; ");
    }
  }
  return "Something went wrong";
}

/**
 * Thin fetch wrapper: prepends the API base URL, attaches the bearer token from the auth store,
 * and normalizes error responses into ApiError. A 401 means the token is dead — clear the session
 * immediately rather than let the app keep sending a token the server will keep rejecting.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().accessToken;
  const isFormData = init.body instanceof FormData;

  const headers = new Headers(init.headers);
  if (!isFormData && init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (res.status === 401) {
    useAuthStore.getState().logout();
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, extractDetail(body));
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export { API_BASE_URL };
