from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from tradeghost.shared.config.settings import Settings


@dataclass
class LLMGenerateResult:
    provider_name: str
    model_name: str
    endpoint: str
    raw_response: str
    parsed_response: dict[str, Any]
    duration_ms: int


@dataclass
class LLMHealthResult:
    provider_name: str
    endpoint: str
    connected: bool
    model_name: str
    model_available: bool | None
    installed_models: list[str]
    error: str | None = None


class LLMProvider(Protocol):
    provider_name: str

    def generate(self, *, prompt: str, model: str, timeout_seconds: float, options: dict[str, Any]) -> LLMGenerateResult:
        ...

    def health_check(self, *, model: str, timeout_seconds: float) -> LLMHealthResult:
        ...


class GroqProvider:
    provider_name = "groq"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, *, prompt: str, model: str, timeout_seconds: float, options: dict[str, Any]) -> LLMGenerateResult:
        if not self.settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY missing")
        endpoint = urljoin(self.settings.groq_base_url.rstrip("/") + "/", "chat/completions")
        payload = {
            "model": model or self.settings.groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(options.get("temperature", 0.1)),
            "max_tokens": int(options.get("num_predict", 120)),
        }
        req = Request(
            url=endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.groq_api_key}",
            },
            method="POST",
        )
        import time

        started = time.perf_counter()
        with urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError("Empty Groq response choices")
        content = str((((choices[0] or {}).get("message") or {}).get("content") or "")).strip()
        if not content:
            raise RuntimeError("Empty Groq content")
        elapsed = int((time.perf_counter() - started) * 1000)
        return LLMGenerateResult(
            provider_name=self.provider_name,
            model_name=payload["model"],
            endpoint=endpoint,
            raw_response=content,
            parsed_response={},
            duration_ms=elapsed,
        )

    def health_check(self, *, model: str, timeout_seconds: float) -> LLMHealthResult:
        endpoint = urljoin(self.settings.groq_base_url.rstrip("/") + "/", "models")
        try:
            req = Request(url=endpoint, method="GET", headers={"Authorization": f"Bearer {self.settings.groq_api_key}"})
            with urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
                if not (200 <= response.status < 300):
                    raise RuntimeError(f"Unexpected status {response.status}")
                body = json.loads(response.read().decode("utf-8"))
            installed = [str(item.get("id")) for item in body.get("data", []) if item.get("id")]
            return LLMHealthResult(
                provider_name=self.provider_name,
                endpoint=endpoint,
                connected=True,
                model_name=model,
                model_available=model in installed if installed else None,
                installed_models=installed[:100],
            )
        except Exception as exc:
            return LLMHealthResult(
                provider_name=self.provider_name,
                endpoint=endpoint,
                connected=False,
                model_name=model,
                model_available=False,
                installed_models=[],
                error=str(exc),
            )


class OllamaProvider:
    provider_name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, *, prompt: str, model: str, timeout_seconds: float, options: dict[str, Any]) -> LLMGenerateResult:
        endpoint = self.settings.ollama_base_url.rstrip("/") + "/api/generate"
        payload = {
            "model": model or self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.settings.ollama_keep_alive,
            "options": options,
        }
        req = Request(
            url=endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        import time

        started = time.perf_counter()
        with urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
        text = str(body.get("response", "")).strip()
        if not text:
            raise RuntimeError("Empty Ollama response")
        elapsed = int((time.perf_counter() - started) * 1000)
        return LLMGenerateResult(
            provider_name=self.provider_name,
            model_name=payload["model"],
            endpoint=endpoint,
            raw_response=text,
            parsed_response={},
            duration_ms=elapsed,
        )

    def health_check(self, *, model: str, timeout_seconds: float) -> LLMHealthResult:
        endpoint = self.settings.ollama_base_url.rstrip("/") + "/api/tags"
        try:
            req = Request(url=endpoint, method="GET")
            with urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
                if not (200 <= response.status < 300):
                    raise RuntimeError(f"Unexpected status {response.status}")
                body = json.loads(response.read().decode("utf-8"))
            installed = [str(item.get("name")) for item in body.get("models", []) if item.get("name")]
            return LLMHealthResult(
                provider_name=self.provider_name,
                endpoint=endpoint,
                connected=True,
                model_name=model,
                model_available=model in installed if installed else None,
                installed_models=installed[:100],
            )
        except Exception as exc:
            return LLMHealthResult(
                provider_name=self.provider_name,
                endpoint=endpoint,
                connected=False,
                model_name=model,
                model_available=False,
                installed_models=[],
                error=str(exc),
            )

