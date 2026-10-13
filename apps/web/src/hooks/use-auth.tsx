"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  getAccessToken,
  getBrandId,
  refreshAccess,
  setAccessToken,
  setBrandId,
} from "@/lib/api";

export type Membership = {
  brand_id: string;
  brand_name: string;
  brand_slug: string;
  role: string;
  can_approve_golden_set: boolean;
  membership_id: string;
};

export type User = {
  id: string;
  email: string;
  name: string;
  locale: string;
  memberships: Membership[];
};

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
  brandId: string | null;
  switchBrand: (id: string) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [brand, setBrand] = useState<string | null>(null);

  const refreshMe = useCallback(async () => {
    let token = getAccessToken();
    if (!token) {
      // New tab / hard reload without access token: restore via refresh cookie
      const ok = await refreshAccess();
      if (!ok) {
        setUser(null);
        return;
      }
      token = getAccessToken();
    }
    if (!token) {
      setUser(null);
      return;
    }
    const me = await api<User>("/me", { skipBrand: true });
    setUser(me);
    const existing = getBrandId();
    const next =
      existing && me.memberships.some((m) => m.brand_id === existing)
        ? existing
        : me.memberships[0]?.brand_id || null;
    setBrandId(next);
    setBrand(next);
  }, []);

  useEffect(() => {
    refreshMe()
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, [refreshMe]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      skipBrand: true,
    });
    setAccessToken(data.access_token);
    setUser(data.user);
    const next = data.user.memberships[0]?.brand_id || null;
    setBrandId(next);
    setBrand(next);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST", skipBrand: true });
    } catch {
      /* ignore */
    }
    setAccessToken(null);
    setBrandId(null);
    setUser(null);
    setBrand(null);
  }, []);

  const switchBrand = useCallback((id: string) => {
    setBrandId(id);
    setBrand(id);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout, refreshMe, brandId: brand, switchBrand }),
    [user, loading, login, logout, refreshMe, brand, switchBrand],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
