"""OpenAI-compatible LLM provider (OpenAI, Groq, OpenRouter, local proxies)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.providers.llm.base import LLMProvider
from app.providers.llm.prompts import METADATA_SYSTEM_PROMPT
from app.schemas.document import ChunkMetadata
from app.utils.json_utils import safe_parse_json

logger = get_logger(__name__)


class OpenAILLMProvider(LLMProvider):
    """LLM provider using the OpenAI Chat Completions API (or compatible base URL)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ProviderError(
                "OPENAI_API_KEY is required for OpenAI LLM provider",
                details={"provider": "openai"},
            )
        self._api_key = settings.openai_api_key
        self._base_url = settings.openai_base_url.rstrip("/")
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens

    async def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, str] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            logger.error("openai_llm_http_error", error=str(exc))
            raise ProviderError(f"OpenAI LLM request failed: {exc}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Unexpected OpenAI response shape: {exc}") from exc

    async def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if schema_hint:
            prompt = f"{prompt}\n\nExpected JSON schema:\n{json.dumps(schema_hint)}"
        messages.append({"role": "user", "content": prompt})
        raw = await self._chat(messages, response_format={"type": "json_object"})
        try:
            return safe_parse_json(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Failed to parse LLM JSON: {exc}", details={"raw": raw[:500]}) from exc

    async def summarize(self, text: str, *, max_words: int = 100) -> str:
        messages = [
            {
                "role": "system",
                "content": f"Summarize the following text in at most {max_words} words. Return plain text only.",
            },
            {"role": "user", "content": text},
        ]
        return (await self._chat(messages)).strip()

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
        user_prompt = f"{context}\n\nText chunk:\n{text}" if context else f"Text chunk:\n{text}"
        data = await self.generate_json(
            user_prompt,
            system=METADATA_SYSTEM_PROMPT,
        )
        # Ensure sourceType from caller if model left it blank
        if source_type and not data.get("sourceType"):
            data["sourceType"] = source_type
        try:
            return ChunkMetadata.model_validate(data)
        except Exception as exc:
            raise ProviderError(f"Invalid metadata schema from LLM: {exc}") from exc
