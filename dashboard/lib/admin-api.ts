/** Client-side helper for calling the admin backend through the proxy.
 *
 * /api/admin/b/<path> -> {BACKEND_URL}/api/admin/<path> with the admin key
 * attached server-side from the admin session cookie.
 */
export async function adminFetch<T = any>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const res = await fetch(`/api/admin/b${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (res.status === 204) return null as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail =
      (data as any)?.detail ?? (typeof data === "string" ? data : `HTTP ${res.status}`);
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return data as T;
}

export const adminApi = {
  listTenants: (query = "") => adminFetch(`/tenants${query ? `?${query}` : ""}`),
  getTenant: (id: string) => adminFetch(`/tenants/${id}`),
  createTenant: (body: object) =>
    adminFetch("/tenants", { method: "POST", body: JSON.stringify(body) }),
  updateTenant: (id: string, body: object) =>
    adminFetch(`/tenants/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  regenerateKey: (id: string) =>
    adminFetch(`/tenants/${id}/regenerate-key`, { method: "POST" }),
  deleteTenant: (id: string) =>
    adminFetch(`/tenants/${id}?confirm=hard`, { method: "DELETE" }),
  documents: (id: string) => adminFetch(`/tenants/${id}/documents`),
  sessions: (id: string) => adminFetch(`/tenants/${id}/sessions`),
  history: (tenantId: string, sessionId: string) =>
    adminFetch(`/tenants/${tenantId}/sessions/${sessionId}`),
};