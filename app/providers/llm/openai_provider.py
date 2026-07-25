"""OpenAI-compatible LLM provider (Ollama, Groq, OpenRouter, OpenAI, local proxies)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.providers.llm.base import LLMProvider
from app.providers.llm.prompts import METADATA_EXAMPLE_JSON, METADATA_SYSTEM_PROMPT
from app.schemas.document import ChunkMetadata
from app.utils.json_utils import safe_parse_json

logger = get_logger(__name__)

# Local CPU inference is slow — keep prompts tiny and generation short
_METADATA_INPUT_CHARS = 1200
_METADATA_MAX_TOKENS = 400
_LOCAL_HTTP_TIMEOUT = 300.0
_REMOTE_HTTP_TIMEOUT = 120.0


def _is_local_base_url(base_url: str) -> bool:
    host = base_url.lower()
    return any(
        token in host
        for token in ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal")
    )


class OpenAILLMProvider(LLMProvider):
    """Chat Completions client for any OpenAI-compatible server (including Ollama)."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.openai_base_url.rstrip("/")
        self._api_key = settings.openai_api_key or "ollama"
        self._local = _is_local_base_url(self._base_url)
        if not settings.openai_api_key and not self._local:
            raise ProviderError(
                "OPENAI_API_KEY is required for remote OpenAI-compatible LLM providers",
                details={"provider": "openai", "base_url": self._base_url},
            )
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens
        configured = float(settings.llm_timeout_seconds)
        self._timeout = configured if self._local else min(configured, _REMOTE_HTTP_TIMEOUT)

    async def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
            # Stream tokens so slow local models keep the HTTP connection alive
            # and avoid long blocking waits on a single non-streaming response.
            "stream": True,
        }
        # Ollama / OpenAI honour `seed`; varying it per question avoids identical decodes.
        if seed is not None:
            payload["seed"] = seed
        # response_format slows / flakes on some Ollama builds — only use remotely
        if response_format and not self._local:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    return (await self._consume_chat_stream(resp)).strip()
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            logger.error(
                "llm_timeout",
                model=self._model,
                base_url=self._base_url,
                timeout=self._timeout,
                error=str(exc) or "timeout",
            )
            raise ProviderError(
                f"LLM ({self._model} @ {self._base_url}) timed out after "
                f"{self._timeout:.0f}s. On CPU/Docker, prefer llama3.2:1b and shorter chunks."
            ) from exc
        except httpx.HTTPError as exc:
            logger.error(
                "llm_http_error",
                model=self._model,
                base_url=self._base_url,
                error=str(exc) or type(exc).__name__,
            )
            raise ProviderError(f"LLM request failed: {exc or type(exc).__name__}") from exc
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Unexpected LLM response shape: {exc}") from exc

    @staticmethod
    async def _consume_chat_stream(resp: httpx.Response) -> str:
        """Accumulate OpenAI-compatible SSE (or NDJSON) chat completion chunks."""
        parts: list[str] = []
        async for line in resp.aiter_lines():
            if not line:
                continue
            payload = line[6:].strip() if line.startswith("data:") else line.strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = data.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if piece is None:
                # Some proxies emit the full message on the final chunk
                message = choice.get("message") or {}
                piece = message.get("content")
            if piece:
                parts.append(piece)
        content = "".join(parts)
        if not content:
            raise ProviderError("LLM stream returned empty content")
        return content

    async def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema_hint: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if schema_hint:
            # Compact example only — never dump full JSON Schema (huge + slow)
            prompt = f"{prompt}\n\nExample JSON shape:\n{json.dumps(schema_hint)}"
        messages.append({"role": "user", "content": prompt})

        raw = await self._chat(
            messages,
            response_format=None if self._local else {"type": "json_object"},
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
        )
        if not raw:
            raise ProviderError("LLM returned empty content")
        try:
            return safe_parse_json(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Failed to parse LLM JSON: {exc}",
                details={"raw": raw[:500]},
            ) from exc

    async def summarize(self, text: str, *, max_words: int = 100) -> str:
        messages = [
            {
                "role": "system",
                "content": f"Summarize the following text in at most {max_words} words. Return plain text only.",
            },
            {"role": "user", "content": text[:_METADATA_INPUT_CHARS]},
        ]
        return (await self._chat(messages, max_tokens=min(256, self._max_tokens))).strip()

    async def extract_metadata(
        self,
        text: str,
        *,
        source_type: str = "",
        exam_code: str = "",
    ) -> ChunkMetadata:
        context_bits = []
        if exam_code:
            context_bits.append(f"Exam: {exam_code}")
        if source_type:
            context_bits.append(f"Source type: {source_type}")
        context = " | ".join(context_bits)
        clipped = text[:_METADATA_INPUT_CHARS]
        user_prompt = (
            f"{context}\n\nText chunk:\n{clipped}" if context else f"Text chunk:\n{clipped}"
        )

        fallback_summary = (clipped[:240] + "…") if len(clipped) > 240 else clipped
        try:
            data = await self.generate_json(
                user_prompt,
                system=METADATA_SYSTEM_PROMPT,
                schema_hint=METADATA_EXAMPLE_JSON,
                max_tokens=_METADATA_MAX_TOKENS,
            )
            if source_type and not data.get("sourceType"):
                data["sourceType"] = source_type
            meta = ChunkMetadata.model_validate(data)
            # Tiny models often return empty or parroted summaries — use extractive text.
            if not (meta.summary or "").strip():
                meta.summary = fallback_summary
            return meta
        except Exception as exc:
            logger.warning(
                "llm_metadata_fallback",
                model=self._model,
                error=str(exc),
            )
            # Soft-fail: keep ingestion moving when local LLM is too slow
            return ChunkMetadata(
                summary=fallback_summary,
                sourceType=source_type or "",
                difficultyHint="unknown",
            )
