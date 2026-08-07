import { NextRequest, NextResponse } from "next/server";

const COOKIE = "konverse_session";

/** Coarse route guard: presence of the session cookie.
 * The real security check is in the proxy Route Handler (jose verification).
 */
export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const authed = !!req.cookies.get(COOKIE)?.value;

  if (pathname === "/login") {
    return authed
      ? NextResponse.redirect(new URL("/documents", req.url))
      : NextResponse.next();
  }
  if (!authed) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/login", "/documents", "/chat", "/sessions"],
};