"""Regulated-industry guardrail interception (Phase 5, hybrid).

Layer 1 (rules): a cheap, deterministic keyword/phrase scan against the
tenant's `guardrail_rules` categories — zero latency, zero tokens, no
embedding/LLM. Layer 2 (escalation) only runs when a rule fires: a tiny Claude
classifier decides refuse-vs-pass, so paraphrases and false-positive keywords
don't block legitimate questions.

If a tenant configures no guardrails (the default) the check passes through
untouched — a zero-cost no-op for the 99% of tenants that opt out.
"""
import logging

from anthropic import AsyncAnthropic

from app.config import Settings
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

GUARDRAIL_REFUSAL = (
    "I'm not able to answer that. This assistant serves this tenant's approved "
    "topics only — please ask something covered by the documentation."
)


class GuardrailDecision:
    __slots__ = ("refused", "category")

    def __init__(self, refused: bool = False, category: str | None = None) -> None:
        self.refused = refused
        self.category = category

    @property
    def message(self) -> str:
        return GUARDRAIL_REFUSAL


def enabled_rules(tenant: Tenant) -> list[tuple[str, str]]:
    """Return [(category, keyword_lower), ...] of the tenant's enabled rules.

    Non-empty only when the tenant deliberately turned guardrails on; this
    drives the cheap rule scan. `guardrail_rules = {enabled:true,
    categories:{<cat>:{keywords:[...], enabled:true}}}`.
    """
    rules = tenant.guardrail_rules or {}
    if not rules.get("enabled", True):  # `enabled:false` opts out entirely
        return []
    categories = rules.get("categories") or {}
    out: list[tuple[str, str]] = []
    for cat, cfg in categories.items():
        if not isinstance(cfg, dict) or not cfg.get("enabled", True):
            continue
        for kw in cfg.get("keywords", []) or []:
            if kw:
                out.append((cat, str(kw).lower()))
    return out


def match_rule(message: str, rules: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Return (category, keyword) of the first rule that fires, else None."""
    text = message.lower()
    for cat, kw in rules:
        if kw in text:
            return cat, kw
    return None


async def _classify(
    settings: Settings, tenant: Tenant, message: str, category: str, keyword: str
) -> bool:
    """Claude classifier: True = refuse, False = pass. Conservative by default.

    On a missing key or any classifier error we REFUSE (True) — for a tenant
    that opted into guardrails, failing closed is safer than letting a
    regulated answer slip through.
    """
    if not settings.anthropic_api_key:
        return True
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    instruction = (
        f"The tenant industry is '{tenant.industry or 'unknown'}'. The user "
        f"message matched guardrail category '{category}' via keyword "
        f"'{keyword}'. Not the category alone guarantees it is regulated, "
        f"evaluate the message intent. Must the assistant REFUSE to answer? "
        f"Reply with exactly YES or NO."
    )
    try:
        resp = await client.messages.create(
            model=settings.guardrail_classifier_model,
            max_tokens=settings.guardrail_classifier_max_tokens,
            system=(
                "You are a strict compliance guard. Refuse only legitimate "
                "regulated content (e.g. medical diagnosis, investment advice)."
            ),
            messages=[{"role": "user", "content": instruction}],
        )
        answer = (resp.content[0].text or "").strip().upper()
        return answer.startswith("YES") if answer else True
    except Exception as exc:  # noqa: BLE001
        logger.warning("guardrail classifier error; refusing (safe): %s", exc)
        return True


async def check_guardrail(
    settings: Settings, tenant: Tenant, message: str
) -> GuardrailDecision:
    """Run the hybrid rule+classifier guard. Returns a refusal/pass decision."""
    rules = enabled_rules(tenant)
    if not rules:
        return GuardrailDecision(refused=False)

    rule = match_rule(message, rules)
    if rule is None:
        return GuardrailDecision(refused=False)

    category, keyword = rule
    refused = await _classify(settings, tenant, message, category, keyword)
    return GuardrailDecision(refused=refused, category=category)