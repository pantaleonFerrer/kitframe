const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080/api/v1";

export type ApiError = {
  error: { code: string; message: string; details?: Record<string, unknown> };
};

const ACCESS_KEY = "kitframe_access";

let accessToken: string | null = null;
let brandId: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (typeof window !== "undefined") {
    // localStorage so new tabs (e.g. Estudio → Crear modelo) keep the session
    if (token) {
      localStorage.setItem(ACCESS_KEY, token);
      sessionStorage.removeItem(ACCESS_KEY);
    } else {
      localStorage.removeItem(ACCESS_KEY);
      sessionStorage.removeItem(ACCESS_KEY);
    }
  }
}

export function getAccessToken() {
  if (accessToken) return accessToken;
  if (typeof window !== "undefined") {
    accessToken =
      localStorage.getItem(ACCESS_KEY) ?? sessionStorage.getItem(ACCESS_KEY);
    // Migrate legacy sessionStorage tokens so they survive new tabs
    if (accessToken && !localStorage.getItem(ACCESS_KEY)) {
      localStorage.setItem(ACCESS_KEY, accessToken);
      sessionStorage.removeItem(ACCESS_KEY);
    }
  }
  return accessToken;
}

export function setBrandId(id: string | null) {
  brandId = id;
  if (typeof window !== "undefined") {
    if (id) localStorage.setItem("kitframe_brand", id);
    else localStorage.removeItem("kitframe_brand");
  }
}

export function getBrandId() {
  if (brandId) return brandId;
  if (typeof window !== "undefined") {
    brandId = localStorage.getItem("kitframe_brand");
  }
  return brandId;
}

export async function refreshAccess(): Promise<boolean> {
  const res = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-Requested-With": "kitframe" },
  });
  if (!res.ok) return false;
  const data = await res.json();
  setAccessToken(data.access_token);
  return true;
}

export async function api<T>(
  path: string,
  init: RequestInit & { skipBrand?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const bid = getBrandId();
  if (bid && !init.skipBrand) headers.set("X-Brand-Id", bid);

  let res = await fetch(`${API_URL}${path}`, { ...init, headers, credentials: "include" });
  if (res.status === 401 && !path.includes("/auth/")) {
    const ok = await refreshAccess();
    if (ok) {
      headers.set("Authorization", `Bearer ${getAccessToken()}`);
      res = await fetch(`${API_URL}${path}`, { ...init, headers, credentials: "include" });
    }
  }
  if (!res.ok) {
    let body: ApiError | null = null;
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    const err = new Error(body?.error?.code || `http_${res.status}`) as Error & {
      code?: string;
      details?: Record<string, unknown>;
      status?: number;
    };
    err.code = body?.error?.code;
    err.details = body?.error?.details;
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
