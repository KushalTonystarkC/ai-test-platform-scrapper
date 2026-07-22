"""API router aggregation."""

from fastapi import APIRouter

from app.api import documents, exams, questions, search

api_router = APIRouter()
api_router.include_router(documents.router)
api_router.include_router(exams.router)
api_router.include_router(questions.router)
api_router.include_router(search.router)
