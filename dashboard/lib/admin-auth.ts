/** Server-side admin session for the admin console.
 *
 * Mirrors the tenant session (lib/auth.ts) but holds the platform ADMIN key in
 * its own HttpOnly cookie so the admin console is fully separate from the
 * tenant-facing `(app)` area. Same signing secret, distinct cookie name.
 */
import { SignJWT, jwtVerify } from "jose";

export const ADMIN_SESSION_COOKIE = "konverse_admin_session";
export const ADMIN_SESSION_MAX_AGE = 12 * 60 * 60; // 12 hours

export type AdminSession = { admin_key: string };

function secret(): Uint8Array {
  const s =
    process.env.SESSION_SECRET ||
    "dev-insecure-secret-change-me";
  return new TextEncoder().encode(s);
}

export async function signAdminSession(adminKey: string): Promise<string> {
  return new SignJWT({ admin_key: adminKey })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("12h")
    .sign(secret());
}

export async function readAdminSession(
  token: string | undefined
): Promise<AdminSession | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, secret());
    return typeof payload.admin_key === "string"
      ? { admin_key: payload.admin_key }
      : null;
  } catch {
    return null;
  }
}