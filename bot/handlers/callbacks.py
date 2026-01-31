"""
Callback query handlers for inline keyboard interactions.

These handlers support the interactive (secondary) interface.
"""

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.services.cloudflare import CloudflareAPI, CloudflareAPIError
from bot.keyboards.inline import (
    get_confirm_keyboard,
    get_proxied_keyboard,
    get_cancel_keyboard,
)
from bot.handlers.states import AddRecordStates, UpdateRecordStates, DeleteRecordStates
from bot.handlers.commands import format_record

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


# ============================================================================
# GENERAL CALLBACKS
# ============================================================================


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle cancel button."""
    await state.clear()
    await callback.message.edit_text("❌ Operation cancelled.")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def callback_noop(callback: CallbackQuery) -> None:
    """Handle no-op buttons (like 'and X more...')."""
    await callback.answer("Use /search or /list to see all records")


# ============================================================================
# ADD RECORD CALLBACKS
# ============================================================================


@router.callback_query(F.data.startswith("type:"))
async def callback_record_type(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle record type selection in add flow."""
    record_type = callback.data.split(":")[1]
    await state.update_data(type=record_type)

    current_state = await state.get_state()

    if current_state == AddRecordStates.waiting_for_type:
        # For A/AAAA/CNAME, ask about proxy status
        if record_type in ("A", "AAAA", "CNAME"):
            await state.set_state(AddRecordStates.waiting_for_proxied)
            await callback.message.edit_text(
                f"📝 Record type: `{record_type}`\n\n"
                "Should this record be proxied through Cloudflare?",
                parse_mode="Markdown",
                reply_markup=get_proxied_keyboard(),
            )
        else:
            # Non-proxyable types, skip to content
            await state.update_data(proxied=False, ttl=1)
            await state.set_state(AddRecordStates.waiting_for_content)
            await callback.message.edit_text(
                f"📝 Record type: `{record_type}`\n\n"
                "Enter the record content:",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard(),
            )

    await callback.answer()


@router.callback_query(F.data.startswith("proxied:"))
async def callback_proxied(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle proxy status selection."""
    proxied = callback.data.split(":")[1] == "true"
    await state.update_data(proxied=proxied, ttl=1)

    current_state = await state.get_state()

    if current_state == AddRecordStates.waiting_for_proxied:
        await state.set_state(AddRecordStates.waiting_for_content)
        proxy_str = "🟠 Proxied" if proxied else "⚪ DNS only"
        await callback.message.edit_text(
            f"📝 Proxy status: {proxy_str}\n\n"
            "Enter the record content (IP address or hostname):",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard(),
        )

    await callback.answer()


# ============================================================================
# UPDATE RECORD CALLBACKS
# ============================================================================


@router.callback_query(F.data.startswith("update_select:"))
async def callback_update_select(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle record selection in interactive update flow."""
    record_id = callback.data.split(":")[1]
    await state.update_data(record_id=record_id)
    await state.set_state(UpdateRecordStates.waiting_for_new_content)

    await callback.message.edit_text(
        "✏️ Enter the new content for this record:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("update_direct:"))
async def callback_update_direct(
    callback: CallbackQuery,
    state: FSMContext,
    cf: CloudflareAPI,
) -> None:
    """Handle record selection for direct update (with pending parameters)."""
    record_id = callback.data.split(":")[1]
    data = await state.get_data()

    content = data.get("pending_content")
    ttl = data.get("pending_ttl")
    proxied = data.get("pending_proxied")

    await state.clear()

    try:
        updated = await cf.update_record(
            record_id=record_id,
            content=content,
            ttl=ttl,
            proxied=proxied,
        )
        await callback.message.edit_text(
            f"✅ **Record Updated!**\n\n{format_record(updated, detailed=True)}",
            parse_mode="Markdown",
        )
    except CloudflareAPIError as e:
        await callback.message.edit_text(f"❌ Error: {e.message}", parse_mode="Markdown")

    await callback.answer()


@router.callback_query(F.data.startswith("update:"))
async def callback_update_action(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Handle update action from record info."""
    record_id = callback.data.split(":")[1]
    await state.update_data(record_id=record_id)
    await state.set_state(UpdateRecordStates.waiting_for_new_content)

    await callback.message.edit_text(
        "✏️ Enter the new content for this record:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


# ============================================================================
# DELETE RECORD CALLBACKS
# ============================================================================


@router.callback_query(F.data.startswith("delete_select:"))
async def callback_delete_select(
    callback: CallbackQuery,
    state: FSMContext,
    cf: CloudflareAPI,
) -> None:
    """Handle record selection in interactive delete flow."""
    record_id = callback.data.split(":")[1]

    try:
        record = await cf.get_record(record_id)
        await state.update_data(delete_record_id=record_id)
        await state.set_state(DeleteRecordStates.confirm)

        await callback.message.edit_text(
            f"⚠️ **Confirm Deletion**\n\n"
            f"Are you sure you want to delete this record?\n\n"
            f"{format_record(record, detailed=True)}",
            parse_mode="Markdown",
            reply_markup=get_confirm_keyboard("delete", record_id),
        )
    except CloudflareAPIError as e:
        await callback.message.edit_text(f"❌ Error: {e.message}", parse_mode="Markdown")

    await callback.answer()


@router.callback_query(F.data.startswith("delete_confirm:"))
async def callback_delete_confirm_select(
    callback: CallbackQuery,
    state: FSMContext,
    cf: CloudflareAPI,
) -> None:
    """Handle record selection from /delete command with multiple matches."""
    record_id = callback.data.split(":")[1]

    try:
        record = await cf.get_record(record_id)
        await state.update_data(delete_record_id=record_id)
        await state.set_state(DeleteRecordStates.confirm)

        await callback.message.edit_text(
            f"⚠️ **Confirm Deletion**\n\n"
            f"Are you sure you want to delete this record?\n\n"
            f"{format_record(record, detailed=True)}",
            parse_mode="Markdown",
            reply_markup=get_confirm_keyboard("delete", record_id),
        )
    except CloudflareAPIError as e:
        await callback.message.edit_text(f"❌ Error: {e.message}", parse_mode="Markdown")

    await callback.answer()


@router.callback_query(F.data.startswith("confirm:delete:"))
async def callback_confirm_delete(
    callback: CallbackQuery,
    state: FSMContext,
    cf: CloudflareAPI,
) -> None:
    """Handle deletion confirmation."""
    record_id = callback.data.split(":")[2]

    try:
        # Get record info before deleting
        record = await cf.get_record(record_id)
        record_name = record.get("name", "Unknown")

        await cf.delete_record(record_id)
        await state.clear()

        await callback.message.edit_text(
            f"✅ **Record Deleted!**\n\n"
            f"Deleted: `{record_name}` ({record.get('type', '?')})",
            parse_mode="Markdown",
        )
    except CloudflareAPIError as e:
        await callback.message.edit_text(f"❌ Error: {e.message}", parse_mode="Markdown")

    await callback.answer()


@router.callback_query(F.data.startswith("delete:"))
async def callback_delete_action(
    callback: CallbackQuery,
    state: FSMContext,
    cf: CloudflareAPI,
) -> None:
    """Handle delete action from record info."""
    record_id = callback.data.split(":")[1]

    try:
        record = await cf.get_record(record_id)
        await state.update_data(delete_record_id=record_id)
        await state.set_state(DeleteRecordStates.confirm)

        await callback.message.edit_text(
            f"⚠️ **Confirm Deletion**\n\n"
            f"Are you sure you want to delete this record?\n\n"
            f"{format_record(record, detailed=True)}",
            parse_mode="Markdown",
            reply_markup=get_confirm_keyboard("delete", record_id),
        )
    except CloudflareAPIError as e:
        await callback.message.edit_text(f"❌ Error: {e.message}", parse_mode="Markdown")

    await callback.answer()


# ============================================================================
# TOGGLE PROXY CALLBACK
# ============================================================================


@router.callback_query(F.data.startswith("toggle_proxy:"))
async def callback_toggle_proxy(callback: CallbackQuery, cf: CloudflareAPI) -> None:
    """Handle toggle proxy from record selection or info."""
    record_id = callback.data.split(":")[1]

    try:
        updated = await cf.toggle_proxy(record_id)
        new_status = "🟠 Proxied" if updated.get("proxied") else "⚪ DNS Only"

        await callback.message.edit_text(
            f"✅ **Proxy Status Toggled!**\n\n"
            f"Record: `{updated['name']}`\n"
            f"New status: {new_status}",
            parse_mode="Markdown",
        )
    except CloudflareAPIError as e:
        await callback.message.edit_text(f"❌ Error: {e.message}", parse_mode="Markdown")

    await callback.answer()


# ============================================================================
# ZONE SELECTION CALLBACK
# ============================================================================


@router.callback_query(F.data.startswith("zone:"))
async def callback_zone_select(callback: CallbackQuery, cf: CloudflareAPI) -> None:
    """Handle zone selection."""
    zone_id = callback.data.split(":")[1]
    cf.default_zone_id = zone_id

    try:
        zone_info = await cf.get_zone_info()
        await callback.message.edit_text(
            f"✅ **Switched to Zone**\n\n"
            f"Name: `{zone_info.get('name', 'Unknown')}`\n"
            f"ID: `{zone_info.get('id', 'N/A')}`",
            parse_mode="Markdown",
        )
    except CloudflareAPIError as e:
        await callback.message.edit_text(f"❌ Error: {e.message}", parse_mode="Markdown")

    await callback.answer()