import { NextRequest, NextResponse } from "next/server";

const TENANT_COOKIE = "konverse_session";
const ADMIN_COOKIE = "konverse_admin_session";

const TENANT_PAGES = ["/documents", "/chat", "/sessions"];

/** Coarse route guard: presence of the relevant session cookie.
 * The real security check is in the proxy Route Handlers (jose verification).
 */
export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const tenantAuthed = !!req.cookies.get(TENANT_COOKIE)?.value;
  const adminAuthed = !!req.cookies.get(ADMIN_COOKIE)?.value;

  // Tenant-facing area.
  if (pathname === "/login") {
    return tenantAuthed
      ? NextResponse.redirect(new URL("/documents", req.url))
      : NextResponse.next();
  }
  if (TENANT_PAGES.includes(pathname)) {
    return tenantAuthed
      ? NextResponse.next()
      : NextResponse.redirect(new URL("/login", req.url));
  }

  // Admin area — separate session, fully isolated from the tenant console.
  if (pathname === "/admin/login") {
    return adminAuthed
      ? NextResponse.redirect(new URL("/admin/tenants", req.url))
      : NextResponse.next();
  }
  if (pathname.startsWith("/admin")) {
    return adminAuthed
      ? NextResponse.next()
      : NextResponse.redirect(new URL("/admin/login", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/login",
    "/documents",
    "/chat",
    "/sessions",
    "/admin",
    "/admin/:path*",
  ],
};