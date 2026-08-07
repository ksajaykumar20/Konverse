import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { readSession, SESSION_COOKIE } from "@/lib/auth";
import { backendBase } from "@/lib/backend";

export const dynamic = "force-dynamic";

// Generic proxy: /api/b/<backend-path> -> {BACKEND_URL}/api/<backend-path>,
// with the tenant's API key attached server-side. Supports SSE streaming for
// the chat endpoint, so the dashboard can render tokens as they arrive.
export async function GET(req: NextRequest) {
  return proxy(req);
}

export async function POST(req: NextRequest) {
  return proxy(req);
}

export async function PATCH(req: NextRequest) {
  return proxy(req);
}

export async function DELETE(req: NextRequest) {
  return proxy(req);
}

async function proxy(req: NextRequest) {
  const session = await readCookie();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const rest = req.nextUrl.pathname.replace(/^\/api\/b\/?/, "");
  const target = `${backendBase()}/api/${rest}${req.nextUrl.search}`;

  const headers = new Headers({ "X-API-Key": session.api_key });
  const incomingCT = req.headers.get("content-type");
  if (incomingCT) headers.set("content-type", incomingCT);

  const init: RequestInit = { method: req.method, headers };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(target, init);

  const out = new Headers();
  const ct = upstream.headers.get("content-type");
  if (ct) out.set("content-type", ct);

  // upstream.body is a ReadableStream; Next pipes it through, so SSE chat
  // streams to the client token-by-token.
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: out,
  });
}

async function readCookie() {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  return readSession(token);
}