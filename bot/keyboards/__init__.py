"""Keyboards package."""

from bot.keyboards.inline import (
    get_record_types_keyboard,
    get_records_keyboard,
    get_confirm_keyboard,
    get_proxied_keyboard,
    get_ttl_keyboard,
    get_cancel_keyboard,
    get_zones_keyboard,
)

__all__ = [
    "get_record_types_keyboard",
    "get_records_keyboard",
    "get_confirm_keyboard",
    "get_proxied_keyboard",
    "get_ttl_keyboard",
    "get_cancel_keyboard",
    "get_zones_keyboard",
]