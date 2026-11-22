from __future__ import annotations

from tradeghost.services.intelligence.providers import OpenAIProvider


def test_gpt_56_normalizes_unsupported_minimal_reasoning_effort() -> None:
    assert OpenAIProvider._reasoning_effort("gpt-5.6", "minimal") == "low"
    assert OpenAIProvider._reasoning_effort("gpt-5.6", None) == "low"


def test_other_reasoning_model_efforts_remain_compatible() -> None:
    assert OpenAIProvider._reasoning_effort("gpt-5.4", "minimal") == "minimal"
    assert OpenAIProvider._reasoning_effort("gpt-5-pro", "low") == "high"
