"""Local filesystem storage for uploaded documents."""

from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger

logger = get_logger(__name__)


class LocalFileStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(self.settings.upload_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def build_path(self, exam_id: uuid.UUID, filename: str) -> Path:
        safe_name = Path(filename).name.replace(" ", "_")
        unique = f"{uuid.uuid4().hex}_{safe_name}"
        directory = self.root / str(exam_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / unique

    async def save(self, destination: Path, data: bytes) -> Path:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(destination, "wb") as f:
                await f.write(data)
            logger.info("file_saved", path=str(destination), size=len(data))
            return destination
        except OSError as exc:
            raise StorageError(f"Failed to save file: {exc}") from exc

    async def read(self, path: Path) -> bytes:
        try:
            async with aiofiles.open(path, "rb") as f:
                return await f.read()
        except OSError as exc:
            raise StorageError(f"Failed to read file: {exc}") from exc

    def delete(self, path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            raise StorageError(f"Failed to delete file: {exc}") from exc
