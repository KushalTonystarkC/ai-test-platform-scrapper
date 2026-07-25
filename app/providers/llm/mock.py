"""Mock LLM provider for local development and tests."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.providers.llm.base import LLMProvider
from app.schemas.document import ChunkMetadata
from app.utils.json_utils import safe_parse_json

# Backwards-compatible alias used by older imports
_safe_parse_json = safe_parse_json


class MockLLMProvider(LLMProvider):
    """Deterministic mock that extracts lightweight heuristics from text."""

    _MOCK_STEMS = [
        "Which body regulates commercial banks in India?",
        "What is the primary function of monetary policy?",
        "Which institution manages India's foreign exchange reserves?",
        "What does the repo rate influence in the economy?",
        "Which body regulates the securities market in India?",
        "What is the main objective of priority sector lending?",
        "Which act governs banking regulation in India?",
        "What does CRR stand for in banking terms?",
    ]

    # Distinct passages so mock runs exercise the shared-stimulus path without
    # tripping the service's duplicate-passage guard.
    _MOCK_SETS: list[tuple[str, list[str]]] = [
        (
            "The central bank reviewed four banks. Bank P held reserves of 4 crore, "
            "Bank Q of 6 crore, Bank R of 3 crore and Bank S of 7 crore. Banks "
            "holding more than 5 crore were exempted from the additional cash "
            "reserve requirement.",
            [
                "How many banks were exempted from the additional cash reserve requirement?",
                "Which bank held the lowest reserves according to the given information?",
                "How many banks held reserves below the exemption threshold?",
                "Which bank held reserves exactly two crore more than Bank R?",
                "How many banks held reserves of more than 4 crore?",
            ],
        ),
        (
            "Five candidates appeared for an interview on consecutive weekdays "
            "starting Monday. Anil attended before Bela but after Chetan. Divya "
            "attended on Friday and Esha attended immediately after Bela.",
            [
                "Who attended the interview on Monday?",
                "On which day did Bela attend the interview?",
                "How many candidates attended after Anil?",
                "Who attended the interview immediately before Divya?",
                "Which candidate attended in the middle of the week?",
            ],
        ),
        (
            "A branch disbursed loans across three quarters. In the first quarter "
            "120 loans were sanctioned, in the second quarter 180 and in the third "
            "quarter 150. Housing loans made up exactly one third of every quarter.",
            [
                "What was the total number of loans sanctioned across the three quarters?",
                "How many housing loans were sanctioned in the second quarter?",
                "Which quarter recorded the highest disbursal of loans?",
                "By how many loans did the second quarter exceed the first?",
                "What fraction of all sanctioned loans were housing loans?",
            ],
        ),
        (
            "A committee of six officers was seated around a circular table facing "
            "the centre. Two officers came from the audit wing, three from the "
            "credit wing and one from the treasury wing. No two audit officers "
            "were seated next to each other.",
            [
                "How many officers on the committee came from the credit wing?",
                "Which wing sent exactly one officer to the committee?",
                "How many officers were seated around the circular table?",
                "How many audit officers could be seated adjacent to each other?",
                "Which wing contributed the largest share of the committee?",
            ],
        ),
    ]

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
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        is_set = bool(schema_hint and "passage" in schema_hint)
        is_mcq = bool(
            schema_hint
            and (
                "questions" in schema_hint
                or ("stem" in schema_hint and "options" in schema_hint)
            )
        )
        # Vary the stem per prompt/seed so mock runs don't produce identical MCQs.
        selector = seed if seed is not None else int(digest, 16)
        if is_set:
            count = self._requested_set_size(prompt)
            option_count = self._requested_option_count(prompt)
            passage, stems = self._MOCK_SETS[selector % len(self._MOCK_SETS)]
            options = (
                ["One", "Two", "Three", "Four", "None of these"]
                if option_count == 5
                else ["One", "Two", "Three", "Four"]
            )
            return {
                "directions": (
                    "Read the passage and answer the questions that follow."
                ),
                "passage": passage,
                "questions": [
                    {
                        "stem": stems[i % len(stems)],
                        "options": options,
                        "correct_index": 1,
                        "explanation": "Derived from the details given in the passage.",
                        "subject": "General Aptitude",
                        "topic": "Comprehension",
                        "difficulty": "medium",
                    }
                    for i in range(count)
                ],
            }
        if is_mcq:
            stem = self._MOCK_STEMS[selector % len(self._MOCK_STEMS)]
            return {
                "stem": stem,
                "options": ["SEBI", "RBI", "IRDAI", "PFRDA"],
                "correct_index": 1,
                "explanation": "RBI is the banking regulator.",
                "subject": "Banking Awareness",
                "topic": "RBI",
                "difficulty": "easy",
            }
        return {"mock": True, "digest": digest, "prompt_length": len(prompt)}

    @staticmethod
    def _requested_set_size(prompt: str) -> int:
        match = re.search(r"Questions in this set:\s*(\d+)", prompt)
        if not match:
            return 3
        return max(1, min(5, int(match.group(1))))

    @staticmethod
    def _requested_option_count(prompt: str) -> int:
        match = re.search(r"Options:\s*(\d+)", prompt)
        if not match:
            return 4
        return 5 if int(match.group(1)) >= 5 else 4

    async def summarize(self, text: str, *, max_words: int = 100) -> str:
        words = text.split()
        snippet = " ".join(words[: min(max_words, 40)])
        return f"{snippet}…" if len(words) > 40 else snippet

    async def extract_metadata(
        self,
        text: str,
        *,
        source_type: str = "",
        exam_code: str = "",
    ) -> ChunkMetadata:
        words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text)
        keywords = list(dict.fromkeys(w.lower() for w in words))[:12]
        concepts = list(dict.fromkeys(w for w in words if w[0].isupper()))[:8]
        summary = await self.summarize(text, max_words=60)
        return ChunkMetadata(
            subject="",
            chapter="",
            topic=concepts[0] if concepts else (keywords[0] if keywords else ""),
            subtopics=keywords[:5],
            keywords=keywords,
            concepts=concepts,
            learningObjectives=[],
            summary=summary,
            difficultyHint="medium",
            sourceType=source_type or "",
        )
