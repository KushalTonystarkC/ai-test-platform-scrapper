"""Configuration package — re-exports settings for a stable import path."""

from app.core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
