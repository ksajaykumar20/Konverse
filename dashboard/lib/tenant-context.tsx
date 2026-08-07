"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";

export type TenantView = {
  id: string;
  name: string;
  industry?: string;
  plan?: string;
};

type Ctx = {
  tenant: TenantView | null;
  loading: boolean;
  error: string | null;
  logout: () => Promise<void>;
};

const TenantCtx = createContext<Ctx>({
  tenant: null,
  loading: true,
  error: null,
  logout: async () => {},
});

export function TenantProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [tenant, setTenant] = useState<TenantView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/me");
        if (!res.ok) {
          setError("Unauthorized");
          return;
        }
        const { tenant: t } = await res.json();
        setTenant({
          id: t.id,
          name: t.name,
          industry: t.industry,
          plan: t.rate_limit_plan,
        });
      } catch {
        setError("Failed to load tenant");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }, [router]);

  return (
    <TenantCtx.Provider value={{ tenant, loading, error, logout }}>
      {children}
    </TenantCtx.Provider>
  );
}

export function useTenant() {
  return useContext(TenantCtx);
}