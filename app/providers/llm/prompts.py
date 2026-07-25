"""Shared LLM prompts."""

METADATA_SYSTEM_PROMPT = """Extract exam-study metadata as ONE JSON object.
Keys: subject, chapter, topic (strings),
subtopics/keywords/concepts/learningObjectives (string arrays),
summary (≤40 words), difficultyHint (easy|medium|hard), sourceType (string).
Max 5 items per array. No markdown. No prose outside JSON.
Derive EVERY field only from the text chunk. Never copy example values.
If a field is unknown, use "" or []."""

# Shape-only example — concrete domain examples get parroted by tiny local models.
METADATA_EXAMPLE_JSON = {
    "subject": "",
    "chapter": "",
    "topic": "",
    "subtopics": [],
    "keywords": [],
    "concepts": [],
    "learningObjectives": [],
    "summary": "",
    "difficultyHint": "medium",
    "sourceType": "BOOK",
}

_QUESTION_SYSTEM_TEMPLATE = """Create exactly 1 multiple-choice question using only the context.
Match the exam's usual style (stem length, option style) from the context — do not force
a banking-exam template if the material is from a different exam.
Return ONE complete JSON object and nothing else (no markdown fences, no prose).
Required keys:
- stem (string question)
- options (array of EXACTLY {option_count} distinct non-empty strings)
- correct_index (integer 0..{max_index})
- explanation, subject, topic, difficulty (strings; difficulty is easy|medium|hard)
Before you finish, count options.length and confirm it equals {option_count}.
Ask about a NEW fact or angle from the context.
Never copy, lightly reword, or paraphrase any question listed in the avoid block,
any question already written in the context, or the example stem."""

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

_COMPREHENSION_SYSTEM_TEMPLATE = """Create ONE shared-stimulus question set for this exam.
Match the exam's usual style from the context (directions wording, passage type,
option count). Do not force banking-exam (IBPS/SBI) templates when the material
belongs to a different exam.
Return ONE complete JSON object and nothing else (no markdown fences, no prose).
Required keys:
- directions (string): short instruction line for the set (empty string if the
  source exam does not use directions headers)
- passage (string): the shared stimulus written ONLY from the context — a short
  comprehension paragraph, puzzle, table summary, caselet, or data set of 60-150
  words. It MUST contain every fact needed to answer all questions.
- questions (array of EXACTLY {count} objects), each with:
  - stem (string) that CANNOT be answered without reading the passage
  - options (array of EXACTLY {option_count} distinct non-empty strings)
  - correct_index (integer 0..{max_index})
  - explanation, subject, topic, difficulty (strings; difficulty is easy|medium|hard)
Rules:
- questions.length must equal {count}; count them before you finish.
- Each question must test a DIFFERENT fact from the passage.
- Never restate the whole passage inside a stem.
- Never copy or paraphrase a question already present in the context or avoid list."""


def question_system_prompt(*, option_count: int = 4) -> str:
    """System prompt for a single standalone MCQ."""
    count = 5 if option_count >= 5 else 4
    return _QUESTION_SYSTEM_TEMPLATE.format(
        option_count=count,
        max_index=count - 1,
    )


def comprehension_system_prompt(count: int, *, option_count: int = 4) -> str:
    """System prompt for a shared-passage set of `count` linked questions."""
    opts = 5 if option_count >= 5 else 4
    return _COMPREHENSION_SYSTEM_TEMPLATE.format(
        count=count,
        option_count=opts,
        max_index=opts - 1,
    )


# Backwards-compatible default (4-option standalone).
QUESTION_SYSTEM_PROMPT = question_system_prompt(option_count=4)

COMPREHENSION_EXAMPLE_JSON = {
    "directions": "Read the passage and answer the questions that follow.",
    "passage": (
        "A research lab tracked four sample groups over one week. Group P had "
        "40 participants, Group Q had 60, Group R had 30 and Group S had 70. "
        "Groups larger than 50 required an extra review step before analysis."
    ),
    "questions": [
        {
            "stem": "How many groups required the extra review step?",
            "options": ["One", "Two", "Three", "Four"],
            "correct_index": 1,
            "explanation": "Groups Q and S had more than 50 participants.",
            "subject": "Quantitative Aptitude",
            "topic": "Data Interpretation",
            "difficulty": "medium",
        }
    ],
}
