import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendBase } from "@/lib/backend";
import {
  ADMIN_SESSION_COOKIE,
  ADMIN_SESSION_MAX_AGE,
  signAdminSession,
} from "@/lib/admin-auth";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let admin_key: string;
  try {
    ({ admin_key } = await req.json());
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }
  if (!admin_key) {
    return NextResponse.json({ error: "Missing admin key" }, { status: 400 });
  }

  // Validate the key against the backend BEFORE minting a session. A failing
  // check means either wrong key (401) or admin disabled server-side (503).
  const backend = await fetch(`${backendBase()}/api/admin/tenants`, {
    headers: { "X-Admin-Key": admin_key },
    cache: "no-store",
  });
  if (backend.status === 503) {
    return NextResponse.json(
      { error: "Admin console is disabled on the backend (set ADMIN_API_KEY)." },
      { status: 503 }
    );
  }
  if (!backend.ok) {
    return NextResponse.json({ error: "Invalid admin key" }, { status: 401 });
  }

  const token = await signAdminSession(admin_key);
  const store = await cookies();
  store.set(ADMIN_SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: ADMIN_SESSION_MAX_AGE,
    path: "/",
  });
  return NextResponse.json({ ok: true });
}