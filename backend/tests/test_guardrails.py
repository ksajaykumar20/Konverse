"""Phase 5 guardrail tests — rule matching + hybrid escalation + HTTP refusal."""
import json

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.models.tenant import Tenant
from app.services import guardrails

API_KEY = "X-API-Key"


def _tenant(rules: dict | None = None) -> Tenant:
    return Tenant(
        name="Hosp",
        slug="hosp",
        industry="healthcare",
        api_key_hash="a" * 64,
        guardrail_rules=rules or {},
    )


def _settings() -> Settings:
    return Settings(
        openai_api_key="x",
        anthropic_api_key="x",
        qdrant_url="http://localhost:1",
        redis_url="redis://localhost:1/0",
        embedding_size=4,
    )


GUARD_RULES = {
    "enabled": True,
    "categories": {
        "medical_diagnosis": {
            "keywords": ["diagnose", "my rash", "symptoms of"],
            "enabled": True,
        },
        "investment_advice": {"keywords": ["buy this stock"], "enabled": True},
        "disabled_cat": {"keywords": ["ignored"], "enabled": False},
    },
}


def test_enabled_rules_opt_in_only():
    rules = enabled = guardrails.enabled_rules(_tenant(GUARD_RULES))
    assert ("medical_diagnosis", "diagnose") in rules
    assert ("investment_advice", "buy this stock") in rules
    # Disabled category and opt-out tenant are excluded.
    assert not any(k == "ignored" for k in enabled)
    assert guardrails.enabled_rules(_tenant({})) == []


def test_enabled_rules_respects_global_opt_out():
    rules = dict(GUARD_RULES, enabled=False)
    assert guardrails.enabled_rules(_tenant(rules)) == []


def test_match_rule_finds_and_misses():
    rules = guardrails.enabled_rules(_tenant(GUARD_RULES))
    assert guardrails.match_rule("can you diagnose this", rules) == (
        "medical_diagnosis",
        "diagnose",
    )
    assert guardrails.match_rule("what is your return policy", rules) is None


@pytest.mark.asyncio
async def test_check_passes_when_no_rules():
    # No rules configured -> passes through without ever hitting _classify.
    decision = await guardrails.check_guardrail(
        _settings(), _tenant(), "anything"
    )
    assert decision.refused is False


@pytest.mark.asyncio
async def test_check_refuses_when_classifier_says_yes(monkeypatch):
    monkeypatch.setattr(guardrails, "_classify", _async_true)
    decision = await guardrails.check_guardrail(
        _settings(), _tenant(GUARD_RULES), "please diagnose my symptoms"
    )
    assert decision.refused is True
    assert decision.category == "medical_diagnosis"


@pytest.mark.asyncio
async def test_check_passes_when_classifier_says_no(monkeypatch):
    monkeypatch.setattr(guardrails, "_classify", _async_false)
    decision = await guardrails.check_guardrail(
        _settings(), _tenant(GUARD_RULES), "please diagnose my symptoms"
    )
    assert decision.refused is False


async def _async_true(*_a, **_k):
    return True


async def _async_false(*_a, **_k):
    return False


async def _create_tenant(client: AsyncClient, rules: dict | None = None) -> dict:
    body = {"name": "Hosp", "industry": "healthcare"}
    if rules is not None:
        body["guardrail_rules"] = rules
    r = await client.post("/api/tenants", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


@pytest.mark.asyncio
async def test_chat_refusal_streams_guardrail_and_logs(client, monkeypatch):
    t = await _create_tenant(client)

    async def fake_check(settings, tenant, message):
        return guardrails.GuardrailDecision(
            refused=True, category="medical_diagnosis"
        )

    monkeypatch.setattr("app.services.guardrails.check_guardrail", fake_check)

    resp = await client.post(
        f"/api/chat/{t['id']}",
        headers={API_KEY: t["api_key"]},
        json={"message": "please diagnose me"},
    )
    assert resp.status_code == 200
    events = _events(resp.text)
    types = [e["type"] for e in events]
    assert "guardrail" in types
    guard_event = next(e for e in events if e["type"] == "guardrail")
    assert guard_event["category"] == "medical_diagnosis"
    done = next(e for e in events if e["type"] == "done")
    assert done["was_answered"] is False

    # The blocked turn is persisted with its category for the dashboard.
    sid = next(e for e in events if e["type"] == "session")["session_id"]
    hist = await client.get(
        f"/api/chat/{t['id']}/history/{sid}", headers={API_KEY: t["api_key"]}
    )
    assert hist.status_code == 200
    msgs = hist.json()["messages"]
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["was_answered"] is False
    assert msgs[1]["guardrail_category"] == "medical_diagnosis"


@pytest.mark.asyncio
async def test_chat_passes_when_guardrail_skips(client, monkeypatch):
    """A tenant with guardrails enabled but a passing classifier reaches RAG."""
    t = await _create_tenant(client, GUARD_RULES)

    async def fake_check(settings, tenant, message):
        return guardrails.GuardrailDecision(refused=False)
    monkeypatch.setattr("app.services.guardrails.check_guardrail", fake_check)

    from app.services.retrieval import RetrievalResult

    async def fake_retrieve(settings, tenant_id, query):
        return RetrievalResult(
            chunks=[{"text": "context", "score": 0.9}], max_score=0.9
        )
    monkeypatch.setattr("app.services.retrieval.retrieve", fake_retrieve)

    async def fake_stream(settings, system_prompt, user_message, chunks=None):
        yield "answered normally"
    monkeypatch.setattr("app.services.llm.stream_answer", fake_stream)

    resp = await client.post(
        f"/api/chat/{t['id']}",
        headers={API_KEY: t["api_key"]},
        json={"message": "please diagnose me"},
    )
    assert resp.status_code == 200
    events = _events(resp.text)
    assert "guardrail" not in [e["type"] for e in events]
    done = next(e for e in events if e["type"] == "done")
    assert done["was_answered"] is True