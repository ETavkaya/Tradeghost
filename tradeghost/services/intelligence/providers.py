from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
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
    token_estimate: int = 0
    status: str = "success"
    fallback_used: bool = False
    error_message: str | None = None


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


class OpenAIProvider:
    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _is_reasoning_model(model: str) -> bool:
        normalized = (model or "").strip().lower()
        return normalized.startswith("gpt-5") or normalized.startswith("o")

    @staticmethod
    def _responses_text_format(response_format: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(response_format, dict) or not response_format:
            return None
        if response_format.get("type") == "json_schema":
            schema_config = response_format.get("json_schema")
            if isinstance(schema_config, dict):
                return {
                    "type": "json_schema",
                    "name": str(schema_config.get("name") or "tradeghost_output"),
                    "schema": schema_config.get("schema") or {},
                    "strict": bool(schema_config.get("strict", False)),
                }
            return response_format
        if response_format.get("type") == "json_object":
            return {"type": "json_object"}
        return None

    @staticmethod
    def _extract_responses_text(body: dict[str, Any]) -> str:
        direct = body.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        chunks: list[str] = []
        output_items = body.get("output")
        if not isinstance(output_items, list):
            return ""
        for item in output_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "output_text" and isinstance(item.get("text"), str):
                chunks.append(item["text"])
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content in content_items:
                if not isinstance(content, dict):
                    continue
                if isinstance(content.get("text"), str):
                    chunks.append(content["text"])
                elif isinstance(content.get("refusal"), str):
                    chunks.append(content["refusal"])
        return "".join(chunks).strip()

    def generate(self, *, prompt: str, model: str, timeout_seconds: float, options: dict[str, Any]) -> LLMGenerateResult:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing")
        endpoint = urljoin(self.settings.openai_base_url.rstrip("/") + "/", "responses")
        model_name = model or self.settings.openai_model
        payload = {
            "model": model_name,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "max_output_tokens": int(options.get("num_predict", 120)),
        }
        text_format = self._responses_text_format(options.get("response_format"))
        if text_format:
            payload["text"] = {"format": text_format}
        if self._is_reasoning_model(model_name):
            effort = str(options.get("reasoning_effort") or "minimal")
            if model_name.lower().startswith("gpt-5-pro"):
                effort = "high"
            payload["reasoning"] = {"effort": effort}
        req = Request(
            url=endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.openai_api_key}",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace").strip()
            detail = error_body[:1200] if error_body else exc.reason
            raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc
        content = self._extract_responses_text(body)
        if not content:
            status = str(body.get("status") or "unknown")
            incomplete = body.get("incomplete_details") or {}
            raise RuntimeError(f"Empty OpenAI content status={status} incomplete_details={incomplete}")
        elapsed = int((time.perf_counter() - started) * 1000)
        usage = body.get("usage") or {}
        token_estimate = int(usage.get("total_tokens", 0) or 0)
        if token_estimate <= 0:
            token_estimate = max(1, int((len(prompt) + len(content)) / 4))
        return LLMGenerateResult(
            provider_name=self.provider_name,
            model_name=model_name,
            endpoint=endpoint,
            raw_response=content,
            parsed_response={"id": body.get("id"), "status": body.get("status")},
            duration_ms=elapsed,
            token_estimate=token_estimate,
        )

    def health_check(self, *, model: str, timeout_seconds: float) -> LLMHealthResult:
        endpoint = urljoin(self.settings.openai_base_url.rstrip("/") + "/", "models")
        try:
            req = Request(url=endpoint, method="GET", headers={"Authorization": f"Bearer {self.settings.openai_api_key}"})
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
            token_estimate=max(1, int((len(prompt) + len(text)) / 4)),
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
