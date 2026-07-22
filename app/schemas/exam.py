"""Pydantic schemas for exams and subjects."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExamCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64, examples=["IBPS_PO"])
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True


class ExamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class ExamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SubjectCreate(BaseModel):
    exam_id: uuid.UUID
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class SubjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    code: str
    name: str
    description: str | None
    created_at: datetime
