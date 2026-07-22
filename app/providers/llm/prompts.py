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

QUESTION_SYSTEM_PROMPT = """You write IBPS-style competitive exam MCQs from study excerpts.
Return ONE JSON object with key "questions" (array).
Each item: stem (string), options (exactly 4 non-empty strings), correct_index (0-3),
explanation (short), subject, topic, difficulty (easy|medium|hard).
Ground answers ONLY in the provided context. When Mode is full_syllabus, vary topics/subjects.
No markdown. No prose outside JSON."""

QUESTION_EXAMPLE_JSON = {
    "questions": [
        {
            "stem": "Which institution regulates banks in India?",
            "options": [
                "SEBI",
                "RBI",
                "IRDAI",
                "NABARD",
            ],
            "correct_index": 1,
            "explanation": "The Reserve Bank of India is the banking regulator.",
            "subject": "Banking Awareness",
            "topic": "RBI",
            "difficulty": "easy",
        }
    ]
}
