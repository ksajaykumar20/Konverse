import { NextRequest, NextResponse } from "next/server";

import { backendBase } from "@/lib/backend";
import {
  SESSION_COOKIE,
  SESSION_MAX_AGE,
  signSession,
} from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let apiKey: string;
  try {
    apiKey = ((await req.json()).apiKey as string | undefined)?.trim() ?? "";
  } catch {
    return NextResponse.json({ error: "Bad request" }, { status: 400 });
  }
  if (!apiKey) {
    return NextResponse.json({ error: "API key required" }, { status: 400 });
  }

  // Validate the key against the backend before issuing a session.
  const backend = await fetch(`${backendBase()}/api/tenants/me`, {
    headers: { "X-API-Key": apiKey },
    cache: "no-store",
  });
  if (!backend.ok) {
    return NextResponse.json({ error: "Invalid API key" }, { status: 401 });
  }
  const tenant = await backend.json();

  const token = await signSession(apiKey);
  const res = NextResponse.json({ tenant });
  res.cookies.set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    // `next start` sets NODE_ENV=production even on http://localhost. Base
    // this on the actual request transport so a local production preview can
    // retain its session, while HTTPS deployments remain protected.
    secure:
      req.nextUrl.protocol === "https:" ||
      req.headers.get("x-forwarded-proto") === "https",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });
  return res;
}
