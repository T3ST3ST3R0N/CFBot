"""Inline keyboard builders for the bot."""

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_record_types_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with DNS record type options."""
    builder = InlineKeyboardBuilder()
    types = ["A", "AAAA", "CNAME", "TXT", "MX", "NS"]

    for rtype in types:
        builder.button(text=rtype, callback_data=f"type:{rtype}")

    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(3, 3, 1)
    return builder.as_markup()


def get_records_keyboard(
    records: list[dict[str, Any]],
    action: str,
    max_display: int = 20,
) -> InlineKeyboardMarkup:
    """
    Create keyboard with DNS records for selection.

    Args:
        records: List of DNS record dictionaries
        action: Action prefix (e.g., 'select', 'delete', 'update')
        max_display: Maximum number of records to display
    """
    builder = InlineKeyboardBuilder()

    for record in records[:max_display]:
        name = record.get("name", "Unknown")
        rtype = record.get("type", "?")
        record_id = record.get("id", "")

        # Truncate long names
        display_name = name if len(name) <= 30 else f"{name[:27]}..."
        button_text = f"{rtype}: {display_name}"

        builder.button(text=button_text, callback_data=f"{action}:{record_id}")

    if len(records) > max_display:
        builder.button(
            text=f"... and {len(records) - max_display} more",
            callback_data="noop",
        )

    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def get_confirm_keyboard(action: str, record_id: str = "") -> InlineKeyboardMarkup:
    """Create confirmation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm", callback_data=f"confirm:{action}:{record_id}")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def get_proxied_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for proxy status selection."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🟠 Proxied (CDN on)", callback_data="proxied:true")
    builder.button(text="⚪ DNS only", callback_data="proxied:false")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(2, 1)
    return builder.as_markup()


def get_ttl_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for TTL selection."""
    builder = InlineKeyboardBuilder()
    ttl_options = [
        ("Auto", "1"),
        ("1 min", "60"),
        ("5 min", "300"),
        ("1 hour", "3600"),
        ("1 day", "86400"),
    ]

    for label, value in ttl_options:
        builder.button(text=label, callback_data=f"ttl:{value}")

    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(3, 2, 1)
    return builder.as_markup()


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Create simple cancel keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data="cancel")
    return builder.as_markup()


def get_zones_keyboard(zones: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Create keyboard with zone selection."""
    builder = InlineKeyboardBuilder()

    for zone in zones[:10]:
        zone_name = zone.get("name", "Unknown")
        zone_id = zone.get("id", "")
        builder.button(text=zone_name, callback_data=f"zone:{zone_id}")

    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def get_record_actions_keyboard(record_id: str) -> InlineKeyboardMarkup:
    """Create keyboard with actions for a specific record."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Update", callback_data=f"update:{record_id}")
    builder.button(text="🔄 Toggle Proxy", callback_data=f"toggle_proxy:{record_id}")
    builder.button(text="🗑️ Delete", callback_data=f"delete:{record_id}")
    builder.button(text="❌ Close", callback_data="cancel")
    builder.adjust(2, 1, 1)
    return builder.as_markup()