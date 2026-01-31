"""Authentication middleware for restricting bot access."""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """
    Middleware that restricts bot access to whitelisted user IDs.

    Users not in the whitelist will receive an "unauthorized" message
    and their requests will not be processed.
    """

    def __init__(self, allowed_user_ids: set[int]):
        """
        Initialize the auth middleware.

        Args:
            allowed_user_ids: Set of Telegram user IDs allowed to use the bot
        """
        self.allowed_user_ids = allowed_user_ids
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the event and check authorization."""
        user_id: int | None = None

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None

        if user_id is None:
            logger.warning("Received event without user information")
            return None

        if user_id not in self.allowed_user_ids:
            logger.warning(f"Unauthorized access attempt from user ID: {user_id}")

            if isinstance(event, Message):
                await event.answer(
                    "⛔ Unauthorized. You are not allowed to use this bot.\n"
                    f"Your user ID: `{user_id}`",
                    parse_mode="Markdown",
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Unauthorized", show_alert=True)

            return None

        return await handler(event, data)