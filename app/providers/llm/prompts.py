"""Shared LLM prompts."""

METADATA_SYSTEM_PROMPT = """Extract exam-study metadata as ONE JSON object.
Keys: subject, chapter, topic (strings), subtopics/keywords/concepts/learningObjectives (string arrays),
summary (≤40 words), difficultyHint (easy|medium|hard), sourceType (string).
Max 5 items per array. No markdown. No prose outside JSON."""

# Compact example — do NOT use full JSON Schema (bloated prompts kill local CPU models)
METADATA_EXAMPLE_JSON = {
    "subject": "Banking Awareness",
    "chapter": "",
    "topic": "RBI",
    "subtopics": ["monetary policy"],
    "keywords": ["RBI", "banks"],
    "concepts": ["regulation"],
    "learningObjectives": [],
    "summary": "RBI regulates banks and monetary policy in India.",
    "difficultyHint": "easy",
    "sourceType": "BOOK",
}
