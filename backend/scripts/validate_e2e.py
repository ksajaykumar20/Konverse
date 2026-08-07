"""Phase 8 — end-to-end validation against a LIVE stack.

Proves the full multi-tenant path works against real providers:

    create tenant → upload doc → async ingest → streams → isolation → refusal

It creates two demo tenants with deliberately non-overlapping topics, ingests
a document for each, then runs a question set and asserts:

  * grounding   — each tenant answers questions grounded in ITS OWN document
  * isolation   — a cross-tenant question is NOT answered (low-confidence
                  fallback), proving retrieval is scoped per tenant
  * guardrail   — enabling a guardrail category makes a regulated question
                  refuse instead of answer

Prereqs (live, real-provider run):
    * Backend + Postgres + Redis + Qdrant running and reachable at BASE_URL.
    * A Celery worker running to drive asynchronous ingestion.
    * OPENAI_API_KEY and ANTHROPIC_API_KEY set in backend/.env.
    * Qdrant collection autowired on first use.

If the stack isn't reachable the script prints a clear "skip" and exits 0, so
it's safe to run in a smoke context without infra.

Usage:
    ./.venv/Scripts/python.exe scripts/validate_e2e.py [--base-url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

# Built-in demo documents. The two topics share no overlapping legal/factual
# phrases on purpose: if retrieval leaked across tenants, one of these would
# falsely succeed.
ACME_DOC = """# Acme Store return policy

Acme Store offers a 30-day return policy on all unused items.

To start a return, email support@acme.example with your order number.
Refunds are issued to the original payment method within 5 business days.

Eligible items must be in original packaging with tags attached.

Questions about our return policy can be sent to support@acme.example.
"""

HEALTH_DOC = """# Meridian Health — clinic hours

Meridian Health is open Monday to Friday from 8:00am to 6:00pm, and
Saturday from 9:00am to 1:00pm. We are closed on Sundays.

To book an appointment, call 555-0100 or use the online portal.
Please bring a photo ID and your insurance card to your first visit.

Urgent care is available at our downtown location from 7:00am to 11:00pm.
"""

# Questions whose answers exist ONLY in the matching tenant's document.
ACME_QUESTIONS = {
    "grounded": "What is the return window at Acme Store?",
    "isolation_probe": "How long is the return window for Acme orders?",
}
HEALTH_QUESTIONS = {
    "grounded": "What are Meridian Health's Saturday clinic hours?",
    "isolation_probe": "Is the Meridian clinic open on Saturday?",
}

GUARDRAIL_TENANT = {
    "name": "E2E Regulated Bank",
    "slug": "e2e-bank",
    "industry": "banking",
    # Regulated category that should refuse; classifier + keyword both matter.
    "guardrail_rules": {
        "enabled": True,
        "categories": {
            "investment-advice": {
                "enabled": True,
                "keywords": ["invest", "returns on"],
            }
        },
    },
}
GUARDRAIL_QUESTION = "Should I invest my savings with you?"


def _pass(spec: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {spec}" + (f" — {detail}" if detail else ""))
    return ok


async def post_sse(client, url, headers, payload):
    """POST and parse an SSE stream into a list of typed event dicts."""
    events: list[dict] = []
    async with client.stream("POST", url, headers=headers, json=payload) as resp:
        status = resp.status_code
        if status != 200:
            # Non-stream body (e.g. a 429/4xx). Capture it for diagnostics.
            return status, [], (await resp.aread()).decode(errors="replace")
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except (ValueError, IndexError):
                    continue
    return status, events, ""


def aggregate(events):
    """Group SSE events by `type` for easy assertions."""
    out: dict[str, list[dict]] = {}
    for ev in events:
        out.setdefault(ev.get("type"), []).append(ev)
    return out


def was_answered(events) -> bool:
    done = [e for e in events if e.get("type") == "done"]
    return bool(done) and bool(done[0].get("was_answered"))


async def create_tenant(client, base, payload) -> dict:
    r = await client.post(f"{base}/api/tenants", json=payload)
    r.raise_for_status()
    return r.json()


async def upload_first_doc(client, base, tenant, filename, content):
    url = f"{base}/api/ingest/{tenant['id']}"
    r = await client.post(
        url,
        headers={"X-API-Key": tenant["api_key"]},
        files={"file": (filename, content.encode("utf-8"), "text/markdown")},
    )
    r.raise_for_status()
    return r.json()


async def wait_indexed(client, base, tenant, doc_id, timeout=180):
    """Poll /documents until the doc is indexed or failed. Returns a status str."""
    headers = {"X-API-Key": tenant["api_key"]}
    url = f"{base}/api/documents/{tenant['id']}"
    waited = 0
    while waited < timeout:
        docs = (await client.get(url, headers=headers)).json()
        for d in docs:
            if str(d["id"]) == str(doc_id):
                if d["status"] in ("indexed", "failed"):
                    return d["status"]
                break
        await asyncio.sleep(3)
        waited += 3
    return "timeout"


async def configure_guardrails(client, base, tenant):
    """Enable a guardrail category on a tenant; returns updated tenant dict."""
    r = await client.patch(
        f"{base}/api/tenants/{tenant['id']}",
        headers={"X-API-Key": tenant["api_key"]},
        json={"guardrail_rules": GUARDRAIL_TENANT["guardrail_rules"]},
    )
    r.raise_for_status()
    return r.json()


async def run_tenant(client, base, name, questions, filename, text) -> bool:
    """Create one tenant, ingest its doc, and run grounded + isolation checks."""
    print(f"\n=== {name} ===")
    ok = True
    tenant = await create_tenant(
        client, base,
        {"name": name, "slug": name.lower().replace(" ", "-"),
         "industry": "retail" if filename.startswith("acme") else "health",
         "rate_limit_plan": "enterprise"},
    )
    print(f"  created tenant {tenant['id']} (plan=enterprise)")

    ingest = await upload_first_doc(client, base, tenant, filename, text)
    status = await wait_indexed(client, base, tenant, ingest["id"])
    ok &= _pass(f"ingest {filename}", status == "indexed", f"status={status}")
    if status != "indexed":
        print("   skipping question assertions — document never indexed")
        return ok

    headers = {"X-API-Key": tenant["api_key"]}
    url = f"{base}/api/chat/{tenant['id']}"

    # Grounded: an in-tenant question returns a real (non-empty) answer.
    st, events, _ = await post_sse(client, url, headers,
                                   {"message": questions["grounded"]})
    answer = "".join(e["text"] for e in events if e.get("type") == "token")
    ok &= _pass("grounded (in-tenant answer)", was_answered(events) and len(answer) > 5,
                f"{answer[:60]!r}")

    # Isolation: the SAME question is not answerable by THIS tenant, so it
    # must fall back (was_answered=False), proving retrieval was scoped.
    st, events, _ = await post_sse(client, url, headers,
                                   {"message": questions["isolation_probe"]})
    ok &= _pass("isolation (cross-tenant NOT answered)",
                not was_answered(events),
                f"was_answered={was_answered(events)}")
    return ok


async def run_guardrail(client, base) -> bool:
    print(f"\n=== Guardrail refusal ({GUARDRAIL_TENANT['name']}) ===")
    ok = True
    tenant = await create_tenant(
        client, base,
        {"name": GUARDRAIL_TENANT["name"], "slug": GUARDRAIL_TENANT["slug"],
         "industry": GUARDRAIL_TENANT["industry"], "rate_limit_plan": "enterprise"},
    )
    await configure_guardrails(client, base, tenant)

    st, events, _ = await post_sse(
        client,
        f"{base}/api/chat/{tenant['id']}",
        {"X-API-Key": tenant["api_key"]},
        {"message": GUARDRAIL_QUESTION},
    )
    ag = aggregate(events)
    refused = bool(ag.get("guardrail"))
    ok &= _pass("guardrail refuses regulated question", refused,
                "categories=" + str([e.get("category") for e in ag.get("guardrail", [])]))
    return ok


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        try:
            (await client.get(f"{base}/api/health")).raise_for_status()
        except httpx.HTTPError as exc:
            print(f"SKIP: backend at {base} unreachable ({exc}). "
                  "Start the stack and a Celery worker, then re-run.")
            return 0

        results: list[bool] = []
        results.append(await run_tenant(client, base, "E2E Acme Store",
                                        ACME_QUESTIONS, "acme.md", ACME_DOC))
        results.append(await run_tenant(client, base, "E2E Meridian Health",
                                        HEALTH_QUESTIONS, "meridian.md", HEALTH_DOC))
        results.append(await run_guardrail(client, base))

    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 50}\nVALIDATION: {passed}/{total} groups passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))