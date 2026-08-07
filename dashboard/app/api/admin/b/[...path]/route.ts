import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { ADMIN_SESSION_COOKIE, readAdminSession } from "@/lib/admin-auth";
import { backendBase } from "@/lib/backend";

export const dynamic = "force-dynamic";

// Generic admin proxy: /api/admin/b/<backend-path> -> {BACKEND_URL}/api/admin/<path>
// with the admin key attached server-side. Admin endpoints are JSON CRUD, so no
// SSE streaming needed here (unlike the tenant chat proxy).
export function GET(req: NextRequest) {
  return proxy(req);
}
export function POST(req: NextRequest) {
  return proxy(req);
}
export function PATCH(req: NextRequest) {
  return proxy(req);
}
export function DELETE(req: NextRequest) {
  return proxy(req);
}

async function proxy(req: NextRequest) {
  const store = await cookies();
  const session = await readAdminSession(store.get(ADMIN_SESSION_COOKIE)?.value);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const rest = req.nextUrl.pathname.replace(/^\/api\/admin\/b\/?/, "");
  const target = `${backendBase()}/api/admin/${rest}${req.nextUrl.search}`;

  const headers = new Headers({ "X-Admin-Key": session.admin_key });
  const incomingCT = req.headers.get("content-type");
  if (incomingCT) headers.set("content-type", incomingCT);

  const init: RequestInit = { method: req.method, headers };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const body = await upstream.text();

  const out = new Headers();
  const ct = upstream.headers.get("content-type");
  if (ct) out.set("content-type", ct);

  return new NextResponse(body, { status: upstream.status, headers: out });
}