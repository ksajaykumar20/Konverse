"""Grounded system-prompt builder + low-confidence fallback text."""
import logging

FALLBACK_TEXT = (
    "I don't have that information in the documents provided for this tenant."
)

logger = logging.getLogger(__name__)


def render_context(chunks: list[dict]) -> str:
    """Render retrieved chunks into the prompt's context block."""
    return "\n\n".join(f"- {c['text']}" for c in chunks)


def build_system_prompt(
    tenant_name: str, system_prompt: str, context: str
) -> str:
    """Ground the assistant strictly to the tenant's retrieved context."""
    policy = system_prompt.strip() or "Be concise, helpful, and grounded."
    return (
        f"You are {tenant_name}'s AI assistant. Answer ONLY from the context "
        f"below. If the context does not contain the answer, say you do not "
        f"know — never invent facts. Do not repeat the context verbatim.\n\n"
        f"Context:\n{context}\n\n"
        f"Assistant policy: {policy}"
    )


def fallback_text() -> str:
    return FALLBACK_TEXT