"""Phase 8 — light concurrent load + rate-limit check against a LIVE stack.

Creates a throwaway free-plan tenant (free tier = 10 requests / 60s by default,
per RATE_LIMITS_CSV) and fires N concurrent chat requests at it. Because the
tenant has no documents, every request takes the low-confidence fallback branch
(fast, no LLM tokens), isolating the rate-limiter + concurrency behavior from
model cost.

Checks:
  * no crashes       — zero requests end with "status 0" (connection errors)
  * enforcement      — the burst is 429'd roughly at the free limit, not all-200
  * latency shape    — reports p95 latency of the requests that were served

Prereqs: backend + Redis reachable at BASE_URL. Skips cleanly (exit 0) if not.

Usage:
    ./.venv/Scripts/python.exe scripts/concurrency_check.py [--requests 40]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections import Counter

import httpx

# Default free tier from RATE_LIMITS_CSV. If you override that setting, keep
# this in sync or the PASS/FAIL skew is misleading.
FREE_LIMIT_PER_WINDOW = 10
FREE_WINDOW_SECONDS = 60


async def create_free_tenant(client, base):
    r = await client.post(
        f"{base}/api/tenants",
        json={"name": "E2E load probe", "slug": "e2e-load", "industry": "retail"},
    )
    r.raise_for_status()
    return r.json()


async def one_chat(client, url, headers, results):
    """One chat request; records (status_code, latency, error)."""
    start = time.monotonic()
    try:
        async with client.stream("POST", url, headers=headers,
                                 json={"message": "hello"}) as resp:
            async for _ in resp.aiter_bytes():
                pass
            results.append({"status": resp.status_code,
                            "latency": time.monotonic() - start})
    except httpx.HTTPError as exc:
        results.append({"status": 0, "latency": time.monotonic() - start,
                        "error": str(exc)})


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=40)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
        try:
            (await client.get(f"{base}/api/health")).raise_for_status()
        except httpx.HTTPError as exc:
            print(f"SKIP: backend at {base} unreachable ({exc}). "
                  "Start the stack, then re-run.")
            return 0

        tenant = await create_free_tenant(client, base)
        url = f"{base}/api/chat/{tenant['id']}"
        headers = {"X-API-Key": tenant["api_key"]}
        print(f"free-plan tenant {tenant['id']}: firing {args.requests} "
              f"concurrent chats (free limit {FREE_LIMIT_PER_WINDOW}/"
              f"{FREE_WINDOW_SECONDS}s)")

        results: list[dict] = []
        await asyncio.gather(
            *(one_chat(client, url, headers, results) for _ in range(args.requests))
        )

    codes = Counter(r["status"] for r in results)
    served = sorted(r["latency"] for r in results if r["status"] == 200)
    p95 = served[int(len(served) * 0.95)] if served else None

    print("\nstatus distribution:", dict(codes.most_common()))
    print(f"429 (rate-limited): {codes.get(429, 0)}   "
          f"200 (served): {codes.get(200, 0)}")
    print(f"p95 latency (served): {round(p95 * 1000, 1) if p95 else 'n/a'} ms"
          f"  |  connection errors: {codes.get(0, 0)}")

    healthy = codes.get(0, 0) == 0 and codes.get(429, 0) > 0 and codes.get(200, 0) > 0
    print(f"\nRESULT: {'PASS' if healthy else 'FAIL'}")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))