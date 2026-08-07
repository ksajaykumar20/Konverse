/** Resolve the Konverse backend base URL (server-side only). */
export function backendBase(): string {
  return (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");
}
