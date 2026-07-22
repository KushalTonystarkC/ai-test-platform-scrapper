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

QUESTION_SYSTEM_PROMPT = """Write 1 IBPS MCQ from context. Return JSON only:
{"questions":[{"stem":"...","options":["choice1","choice2","choice3","choice4"],"correct_index":1,"explanation":"≤12 words","subject":"...","topic":"...","difficulty":"medium"}]}
Rules: options MUST be exactly 4 full answer choices. correct_index is REQUIRED (0-3 integer). Ground ONLY in context. Complete the JSON."""

QUESTION_EXAMPLE_JSON = {
    "questions": [
        {
            "stem": "Which body regulates banks in India?",
            "options": ["SEBI", "RBI", "IRDAI", "NABARD"],
            "correct_index": 1,
            "explanation": "RBI is the banking regulator.",
            "subject": "Banking Awareness",
            "topic": "RBI",
            "difficulty": "easy",
        }
    ]
}
