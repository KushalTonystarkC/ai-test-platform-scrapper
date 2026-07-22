"""Shared enums for domain models."""

from enum import StrEnum


class DocumentType(StrEnum):
    BOOK = "BOOK"
    PREVIOUS_YEAR_PAPER = "PREVIOUS_YEAR_PAPER"
    SYLLABUS = "SYLLABUS"


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class SearchMode(StrEnum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class DifficultyHint(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
