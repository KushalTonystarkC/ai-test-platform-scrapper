"""Domain and application exceptions with HTTP mapping."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base application error."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "app_error",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", **kwargs: Any) -> None:
        super().__init__(message, code="not_found", status_code=404, **kwargs)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation failed", **kwargs: Any) -> None:
        super().__init__(message, code="validation_error", status_code=422, **kwargs)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", **kwargs: Any) -> None:
        super().__init__(message, code="conflict", status_code=409, **kwargs)


class ProcessingError(AppError):
    def __init__(self, message: str = "Processing failed", **kwargs: Any) -> None:
        super().__init__(message, code="processing_error", status_code=500, **kwargs)


class ProviderError(AppError):
    def __init__(self, message: str = "Provider error", **kwargs: Any) -> None:
        super().__init__(message, code="provider_error", status_code=502, **kwargs)


class StorageError(AppError):
    def __init__(self, message: str = "Storage error", **kwargs: Any) -> None:
        super().__init__(message, code="storage_error", status_code=500, **kwargs)
