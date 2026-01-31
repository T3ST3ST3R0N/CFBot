"""Handlers package."""

from bot.handlers.commands import router as commands_router
from bot.handlers.callbacks import router as callbacks_router

__all__ = ["commands_router", "callbacks_router"]