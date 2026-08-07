import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { readSession, SESSION_COOKIE } from "@/lib/auth";
import { backendBase } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  const session = await readSession(token);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const backend = await fetch(`${backendBase()}/api/tenants/me`, {
    headers: { "X-API-Key": session.api_key },
    cache: "no-store",
  });
  if (!backend.ok) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const tenant = await backend.json();
  return NextResponse.json({ tenant });
}