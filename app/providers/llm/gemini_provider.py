"""Google Gemini LLM provider via the official google-genai SDK."""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.providers.llm.base import LLMProvider
from app.providers.llm.prompts import METADATA_SYSTEM_PROMPT
from app.schemas.document import ChunkMetadata
from app.utils.json_utils import safe_parse_json

logger = get_logger(__name__)

# Keep metadata prompts compact so responses fit within token limits.
_METADATA_INPUT_CHARS = 3500
_METADATA_MAX_OUTPUT_TOKENS = 2048


class GeminiLLMProvider(LLMProvider):
    """LLM provider using Gemini generate_content (async)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise ProviderError(
                "GEMINI_API_KEY is required for Gemini LLM provider",
                details={"provider": "gemini"},
            )
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def _generate(
        self,
        contents: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
        response_schema: type | dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> str:
        config_kwargs: dict[str, Any] = {
            "temperature": temperature if temperature is not None else self._temperature,
            "max_output_tokens": max_output_tokens or self._max_tokens,
        }
        if seed is not None:
            config_kwargs["seed"] = seed
        if system:
            config_kwargs["system_instruction"] = system
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:
            logger.error("gemini_llm_error", error=str(exc))
            raise ProviderError(f"Gemini LLM request failed: {exc}") from exc

        text = (response.text or "").strip()
        if not text:
            raise ProviderError("Gemini returned an empty response")
        return text

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
        if schema_hint:
            prompt = f"{prompt}\n\nExpected JSON schema:\n{json.dumps(schema_hint)}"
        raw = await self._generate(
            prompt,
            system=system,
            json_mode=True,
            max_output_tokens=max_tokens
            or max(self._max_tokens, _METADATA_MAX_OUTPUT_TOKENS),
            temperature=temperature,
            seed=seed,
        )
        try:
            return safe_parse_json(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Failed to parse Gemini JSON: {exc}",
                details={"raw": raw[:500]},
            ) from exc

    async def summarize(self, text: str, *, max_words: int = 100) -> str:
        system = (
            f"Summarize the following text in at most {max_words} words. "
            "Return plain text only."
        )
        return await self._generate(text, system=system, json_mode=False)

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

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw = await self._generate(
                    user_prompt,
                    system=METADATA_SYSTEM_PROMPT,
                    response_schema=ChunkMetadata,
                    max_output_tokens=_METADATA_MAX_OUTPUT_TOKENS,
                )
                data = safe_parse_json(raw)
                if source_type and not data.get("sourceType"):
                    data["sourceType"] = source_type
                return ChunkMetadata.model_validate(data)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "gemini_metadata_attempt_failed",
                    attempt=attempt + 1,
                    error=str(exc),
                )

        logger.error("gemini_metadata_fallback", error=str(last_error))
        # Do not fail the whole document for one bad LLM response
        return ChunkMetadata(
            summary=(clipped[:240] + "…") if len(clipped) > 240 else clipped,
            sourceType=source_type or "",
            difficultyHint="unknown",
        )
