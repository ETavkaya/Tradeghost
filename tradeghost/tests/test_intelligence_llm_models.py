from __future__ import annotations

from types import SimpleNamespace

from tradeghost.services.intelligence.service import IntelligenceService


def _make_service() -> IntelligenceService:
    service = IntelligenceService.__new__(IntelligenceService)
    service.settings = SimpleNamespace(
        llmq_chat_model="gpt-4o-mini",
        daily_report_llm_model="gpt-4o-mini",
        market_context_llm_model="gpt-4o-mini",
        final_28d_review_llm_model="gpt-4o-mini",
        openai_model="gpt-4o-mini",
        ollama_model="llama3.2:3b",
    )
    return service


def test_default_model_for_provider_uses_llm_chat_model() -> None:
    service = _make_service()

    assert service._default_model_for_provider("openai") == "gpt-4o-mini"
    assert service._default_model_for_provider("ollama") == "llama3.2:3b"


def test_resolve_openai_model_uses_installed_fallback_when_requested_model_is_missing() -> None:
    service = _make_service()

    model, available = service._resolve_openai_model("gpt-5.4-mini", ["gpt-4o-mini", "gpt-4.1-mini"])

    assert model == "gpt-4o-mini"
    assert available is True


def test_resolve_openai_model_preserves_requested_model_when_available() -> None:
    service = _make_service()

    model, available = service._resolve_openai_model("gpt-4o-mini", ["gpt-4o-mini", "gpt-4.1-mini"])

    assert model == "gpt-4o-mini"
    assert available is True
