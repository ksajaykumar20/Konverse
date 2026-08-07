/** Server-side session auth for the dashboard.
 *
 * The tenant's API key is held ONLY here, on the Next.js server, and signed
 * into an HttpOnly cookie. It never reaches browser JS — XSS cannot exfiltrate
 * it. Every backend call is made server-side with the key attached.
 */
import { SignJWT, jwtVerify } from "jose";

export const SESSION_COOKIE = "konverse_session";
export const SESSION_MAX_AGE = 12 * 60 * 60; // 12 hours

export type Session = { api_key: string };

function secret(): Uint8Array {
  const s =
    process.env.SESSION_SECRET ||
    // Dev-only fallback. In production this MUST be set to a long secret.
    "dev-insecure-secret-change-me";
  return new TextEncoder().encode(s);
}

export async function signSession(apiKey: string): Promise<string> {
  return new SignJWT({ api_key: apiKey })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("12h")
    .sign(secret());
}

export async function readSession(
  token: string | undefined
): Promise<Session | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, secret());
    return typeof payload.api_key === "string"
      ? { api_key: payload.api_key }
      : null;
  } catch {
    return null;
  }
}