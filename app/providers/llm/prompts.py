"""Shared LLM prompts."""

METADATA_SYSTEM_PROMPT = """Extract exam-study metadata as ONE JSON object.
Keys: subject, chapter, topic (strings),
subtopics/keywords/concepts/learningObjectives (string arrays),
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

QUESTION_SYSTEM_PROMPT = """Create exactly 1 IBPS-style MCQ using only the context.
Return ONE complete JSON object and nothing else (no markdown fences, no prose).
Required keys:
- stem (string question)
- options (array of EXACTLY 4 distinct non-empty strings)
- correct_index (integer 0, 1, 2, or 3)
- explanation, subject, topic, difficulty (strings; difficulty is easy|medium|hard)
Before you finish, count options.length and confirm it equals 4.
Ask about a new context fact; never copy or paraphrase the example."""

# Flat single-object example: nested `questions: [...]` confuses small local models
# into emitting incomplete / multi-item payloads.
QUESTION_EXAMPLE_JSON = {
    "stem": "Which planet is known as the Red Planet?",
    "options": ["Venus", "Mars", "Jupiter", "Mercury"],
    "correct_index": 1,
    "explanation": "Mars appears red because of iron oxide.",
    "subject": "General Knowledge",
    "topic": "Astronomy",
    "difficulty": "medium",
}
