const ACCESS_TOKEN_KEY = "kitframe_access_token";
const ACTIVE_BRAND_KEY = "kitframe_active_brand";
const SIDEBAR_COLLAPSED_KEY = "kitframe_sidebar_collapsed";

function tokenStore(remember = true): Storage {
  if (typeof window === "undefined") {
    return {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
      clear: () => undefined,
      key: () => null,
      length: 0,
    };
  }
  return remember ? localStorage : sessionStorage;
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return (
    localStorage.getItem(ACCESS_TOKEN_KEY) ??
    sessionStorage.getItem(ACCESS_TOKEN_KEY)
  );
}

export function setAccessToken(token: string, remember = true): void {
  const other = remember ? sessionStorage : localStorage;
  other.removeItem(ACCESS_TOKEN_KEY);
  tokenStore(remember).setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getActiveBrandId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACTIVE_BRAND_KEY);
}

export function setActiveBrandId(brandId: string): void {
  localStorage.setItem(ACTIVE_BRAND_KEY, brandId);
}

export function getSidebarCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
}

export function setSidebarCollapsed(collapsed: boolean): void {
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
}
