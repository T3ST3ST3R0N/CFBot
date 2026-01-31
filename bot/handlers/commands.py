"""
Command handlers for the Cloudflare DNS bot.

DESIGN: Single-line commands are the PRIMARY interface for users with poor connectivity.
Interactive flows are SECONDARY and provided for convenience.
"""

import json
import logging
from html import escape
from typing import Any

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.services.cloudflare import CloudflareAPI, CloudflareAPIError, VALID_RECORD_TYPES
from bot.keyboards.inline import (
    get_record_types_keyboard,
    get_records_keyboard,
    get_confirm_keyboard,
    get_cancel_keyboard,
)
from bot.handlers.states import AddRecordStates, UpdateRecordStates, DeleteRecordStates

logger = logging.getLogger(__name__)
router = Router(name="commands")


def format_record(record: dict[str, Any], detailed: bool = False) -> str:
    """Format a DNS record for display (HTML)."""
    name = escape(record.get("name", "Unknown"))
    rtype = escape(record.get("type", "?"))
    content = escape(record.get("content", "?"))
    ttl = record.get("ttl", 1)
    proxied = record.get("proxied", False)

    ttl_str = "Auto" if ttl == 1 else f"{ttl}s"
    proxy_icon = "🟠" if proxied else "⚪"

    if detailed:
        record_id = escape(record.get("id", "N/A"))
        created = record.get("created_on", "N/A")[:10] if record.get("created_on") else "N/A"
        modified = record.get("modified_on", "N/A")[:10] if record.get("modified_on") else "N/A"

        return (
            f"📝 <b>{name}</b>\n"
            f"├ Type: <code>{rtype}</code>\n"
            f"├ Content: <code>{content}</code>\n"
            f"├ TTL: {ttl_str}\n"
            f"├ Proxied: {proxy_icon} {'Yes' if proxied else 'No'}\n"
            f"├ ID: <code>{record_id}</code>\n"
            f"├ Created: {created}\n"
            f"└ Modified: {modified}"
        )

    # Compact format for lists
    return f"{proxy_icon} <code>{rtype:5}</code> {name} → <code>{content}</code> (TTL: {ttl_str})"


def format_records_list(records: list[dict[str, Any]], title: str = "DNS Records") -> str:
    """Format a list of records for display (HTML)."""
    if not records:
        return f"📋 <b>{escape(title)}</b>\n\nNo records found."

    lines = [f"📋 <b>{escape(title)}</b> ({len(records)} records)\n"]
    for record in records:
        lines.append(format_record(record))

    return "\n".join(lines)


def parse_bool(value: str) -> bool:
    """Parse a boolean from string."""
    return value.lower() in ("true", "yes", "1", "on", "y")


async def require_zone(message: Message, cf: CloudflareAPI) -> bool:
    """
    Check if a zone is selected. If not, prompt user to select one.
    Returns True if zone is available, False if user needs to select.
    """
    if cf.default_zone_id:
        return True

    await message.answer(
        "⚠️ <b>No zone selected!</b>\n\n"
        "Please select a zone first:\n"
        "• /zones - List all your domains\n"
        "• /zone &lt;domain&gt; - Select by domain name",
        parse_mode="HTML",
    )
    return False


# ============================================================================
# BASIC COMMANDS
# ============================================================================


@router.message(CommandStart())
async def cmd_start(message: Message, cf: CloudflareAPI) -> None:
    """Handle /start command."""
    zone_name = None
    if cf.default_zone_id:
        try:
            zone_info = await cf.get_zone_info()
            zone_name = zone_info.get("name")
        except CloudflareAPIError:
            pass

    if zone_name:
        await message.answer(
            "👋 <b>Cloudflare DNS Manager Bot</b>\n\n"
            f"🌐 Current zone: <code>{escape(zone_name)}</code>\n\n"
            "<b>Quick Commands:</b>\n"
            "• /list - List all DNS records\n"
            "• /list A - List only A records\n"
            "• /add sub A 1.2.3.4 - Add record\n"
            "• /update sub 5.6.7.8 - Update record\n"
            "• /delete sub - Delete record\n"
            "• /search keyword - Search records\n"
            "• /zones - Switch domain\n"
            "• /help - Full usage guide\n\n"
            "💡 <i>Single-line commands work best with slow connections!</i>",
            parse_mode="HTML",
        )
    else:
        # No zone selected - show zone list
        try:
            zones = await cf.list_zones()
            if zones:
                lines = [
                    "👋 <b>Cloudflare DNS Manager Bot</b>\n\n"
                    "⚠️ <b>Select a domain to manage:</b>\n"
                ]
                for zone in zones[:15]:
                    name = escape(zone.get("name", "Unknown"))
                    lines.append(f"• <code>/zone {name}</code>")

                lines.append("\n<i>Use /help for all commands</i>")
                await message.answer("\n".join(lines), parse_mode="HTML")
            else:
                await message.answer(
                    "👋 <b>Cloudflare DNS Manager Bot</b>\n\n"
                    "❌ No zones found with your API token.\n"
                    "Check your CLOUDFLARE_API_TOKEN permissions.",
                    parse_mode="HTML",
                )
        except CloudflareAPIError as e:
            await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command with detailed usage guide."""
    help_text = """📖 <b>Cloudflare DNS Bot - Help</b>

<b>LISTING RECORDS:</b>
<pre>
/list           - List all records
/list A         - List only A records
/list CNAME     - List only CNAME records
</pre>

<b>ADDING RECORDS:</b>
<pre>/add &lt;name&gt; &lt;type&gt; &lt;content&gt; [ttl] [proxied]</pre>
Examples:
• /add sub A 1.2.3.4
• /add sub A 1.2.3.4 3600 true
• /add www CNAME example.com
• /add mail MX mail.server.com

<b>UPDATING RECORDS:</b>
<pre>/update &lt;name&gt; &lt;content&gt; [ttl] [proxied]</pre>
Examples:
• /update sub 5.6.7.8
• /update sub 5.6.7.8 3600
• /update sub 5.6.7.8 auto false

<b>DELETING RECORDS:</b>
<pre>/delete &lt;name&gt; [type]</pre>
Examples:
• /delete sub - Delete if only one record
• /delete sub A - Delete specific type

<b>OTHER COMMANDS:</b>
• /search query - Search by name
• /info name - Show record details
• /toggle_proxy name - Toggle CDN proxy
• /zones - List available zones
• /zone domain - Switch zone
• /export [type] - Export records as JSON

<b>INTERACTIVE MODE:</b>
Use commands without arguments for guided flow:
• /add - Interactive add wizard
• /update - Interactive update wizard
• /delete - Interactive delete wizard

<b>TIPS:</b>
• TTL: Use seconds (3600) or "auto" for automatic
• Proxied: "true"/"false" - only for A/AAAA/CNAME
• Name: Use short name (sub) or full (sub.example.com)

<b>Record Types:</b> A, AAAA, CNAME, TXT, MX, NS, SRV, CAA"""

    await message.answer(help_text, parse_mode="HTML")


# ============================================================================
# LIST / SEARCH / INFO COMMANDS
# ============================================================================


@router.message(Command("list"))
async def cmd_list(message: Message, cf: CloudflareAPI) -> None:
    """
    List DNS records, optionally filtered by type.

    Usage:
        /list           - List all records
        /list A         - List only A records
        /list CNAME     - List only CNAME records
    """
    if not await require_zone(message, cf):
        return

    args = message.text.split()[1:] if message.text else []
    record_type = args[0].upper() if args else None

    if record_type and record_type not in VALID_RECORD_TYPES:
        await message.answer(
            f"❌ Invalid record type: <code>{escape(record_type)}</code>\n"
            f"Valid types: {', '.join(sorted(VALID_RECORD_TYPES))}",
            parse_mode="HTML",
        )
        return

    try:
        records = await cf.list_records(record_type=record_type)
        title = f"{record_type} Records" if record_type else "All DNS Records"
        await message.answer(format_records_list(records, title), parse_mode="HTML")
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


@router.message(Command("search"))
async def cmd_search(message: Message, cf: CloudflareAPI) -> None:
    """
    Search DNS records by name.

    Usage:
        /search sub     - Find records containing "sub"
        /search mail    - Find records containing "mail"
    """
    if not await require_zone(message, cf):
        return

    args = message.text.split()[1:] if message.text else []

    if not args:
        await message.answer(
            "❌ Usage: /search &lt;query&gt;\n"
            "Example: /search sub",
            parse_mode="HTML",
        )
        return

    query = args[0]

    try:
        records = await cf.find_records_by_name(query)
        title = f"Search Results for '{query}'"
        await message.answer(format_records_list(records, title), parse_mode="HTML")
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


@router.message(Command("info"))
async def cmd_info(message: Message, cf: CloudflareAPI) -> None:
    """
    Show detailed info about a DNS record.

    Usage:
        /info sub.example.com
        /info sub
    """
    if not await require_zone(message, cf):
        return

    args = message.text.split()[1:] if message.text else []

    if not args:
        await message.answer(
            "❌ Usage: /info &lt;record_name&gt;\n"
            "Example: /info sub.example.com",
            parse_mode="HTML",
        )
        return

    name = args[0]

    try:
        records = await cf.find_records_by_name(name)

        if not records:
            await message.answer(f"❌ No records found matching <code>{escape(name)}</code>", parse_mode="HTML")
            return

        # Show all matching records with detailed info
        lines = [f"🔍 <b>Records matching '{escape(name)}'</b>\n"]
        for record in records:
            lines.append(format_record(record, detailed=True))
            lines.append("")

        await message.answer("\n".join(lines), parse_mode="HTML")
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


# ============================================================================
# ADD COMMAND (Single-line + Interactive)
# ============================================================================


@router.message(Command("add"))
async def cmd_add(message: Message, cf: CloudflareAPI, state: FSMContext) -> None:
    """
    Add a new DNS record.

    Single-line usage (preferred for slow connections):
        /add <name> <type> <content> [ttl] [proxied]

    Examples:
        /add sub A 1.2.3.4
        /add sub A 1.2.3.4 3600 true
        /add www CNAME example.com
        /add mail MX mailserver.com

    Interactive usage:
        /add    (without arguments starts interactive flow)
    """
    if not await require_zone(message, cf):
        return

    args = message.text.split()[1:] if message.text else []

    # Interactive mode if no arguments
    if not args:
        await state.set_state(AddRecordStates.waiting_for_name)
        await message.answer(
            "📝 <b>Add DNS Record</b> (Interactive Mode)\n\n"
            "Enter the record name (e.g., <code>sub</code> or <code>sub.example.com</code>):\n\n"
            "<i>Or use single-line command:</i>\n"
            "<code>/add name type content [ttl] [proxied]</code>",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
        return

    # Single-line mode - parse arguments
    if len(args) < 3:
        await message.answer(
            "❌ Not enough arguments.\n\n"
            "Usage: /add &lt;name&gt; &lt;type&gt; &lt;content&gt; [ttl] [proxied]\n\n"
            "Examples:\n"
            "• /add sub A 1.2.3.4\n"
            "• /add sub A 1.2.3.4 3600 true\n"
            "• /add www CNAME example.com",
            parse_mode="HTML",
        )
        return

    name = args[0]
    record_type = args[1].upper()
    content = args[2]
    ttl = 1  # Auto
    proxied = False

    # Validate record type
    if record_type not in VALID_RECORD_TYPES:
        await message.answer(
            f"❌ Invalid record type: <code>{escape(record_type)}</code>\n"
            f"Valid types: {', '.join(sorted(VALID_RECORD_TYPES))}",
            parse_mode="HTML",
        )
        return

    # Parse optional TTL
    if len(args) > 3:
        ttl_arg = args[3].lower()
        if ttl_arg == "auto":
            ttl = 1
        else:
            try:
                ttl = int(ttl_arg)
            except ValueError:
                await message.answer(
                    f"❌ Invalid TTL: <code>{escape(args[3])}</code>\n"
                    "Use a number (seconds) or 'auto'",
                    parse_mode="HTML",
                )
                return

    # Parse optional proxied
    if len(args) > 4:
        proxied = parse_bool(args[4])

    # Create the record
    try:
        record = await cf.create_record(
            name=name,
            record_type=record_type,
            content=content,
            ttl=ttl,
            proxied=proxied,
        )
        await message.answer(
            f"✅ <b>Record Created Successfully!</b>\n\n{format_record(record, detailed=True)}",
            parse_mode="HTML",
        )
    except CloudflareAPIError as e:
        await message.answer(f"❌ Failed to create record: {escape(e.message)}", parse_mode="HTML")


# ============================================================================
# UPDATE COMMAND (Single-line + Interactive)
# ============================================================================


@router.message(Command("update"))
async def cmd_update(message: Message, cf: CloudflareAPI, state: FSMContext) -> None:
    """
    Update an existing DNS record.

    Single-line usage (preferred):
        /update <name> <new_content> [ttl] [proxied]

    Examples:
        /update sub 5.6.7.8
        /update sub 5.6.7.8 3600
        /update sub 5.6.7.8 auto false

    Interactive usage:
        /update    (without arguments)
    """
    if not await require_zone(message, cf):
        return

    args = message.text.split()[1:] if message.text else []

    # Interactive mode
    if not args:
        try:
            records = await cf.list_records()
            if not records:
                await message.answer("❌ No DNS records found.", parse_mode="HTML")
                return

            await state.set_state(UpdateRecordStates.waiting_for_record_selection)
            await message.answer(
                "✏️ <b>Update DNS Record</b> (Interactive Mode)\n\n"
                "Select a record to update:\n\n"
                "<i>Or use single-line command:</i>\n"
                "<code>/update name content [ttl] [proxied]</code>",
                parse_mode="HTML",
                reply_markup=get_records_keyboard(records, "update_select"),
            )
        except CloudflareAPIError as e:
            await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")
        return

    # Single-line mode
    if len(args) < 2:
        await message.answer(
            "❌ Not enough arguments.\n\n"
            "Usage: /update &lt;name&gt; &lt;content&gt; [ttl] [proxied]\n\n"
            "Examples:\n"
            "• /update sub 5.6.7.8\n"
            "• /update sub 5.6.7.8 3600 true",
            parse_mode="HTML",
        )
        return

    name = args[0]
    new_content = args[1]
    ttl: int | None = None
    proxied: bool | None = None

    # Parse optional TTL
    if len(args) > 2:
        ttl_arg = args[2].lower()
        if ttl_arg == "auto":
            ttl = 1
        else:
            try:
                ttl = int(ttl_arg)
            except ValueError:
                await message.answer(
                    f"❌ Invalid TTL: <code>{escape(args[2])}</code>",
                    parse_mode="HTML",
                )
                return

    # Parse optional proxied
    if len(args) > 3:
        proxied = parse_bool(args[3])

    # Find the record
    try:
        records = await cf.find_records_by_name(name)

        if not records:
            await message.answer(f"❌ No record found matching <code>{escape(name)}</code>", parse_mode="HTML")
            return

        if len(records) > 1:
            # Multiple matches - show selection
            await message.answer(
                f"⚠️ Found {len(records)} records matching <code>{escape(name)}</code>.\n"
                "Please select which one to update:",
                parse_mode="HTML",
                reply_markup=get_records_keyboard(records, "update_direct"),
            )
            # Store the update parameters for callback
            await state.update_data(
                pending_content=new_content,
                pending_ttl=ttl,
                pending_proxied=proxied,
            )
            await state.set_state(UpdateRecordStates.waiting_for_record_selection)
            return

        # Single match - update directly
        record = records[0]
        updated = await cf.update_record(
            record_id=record["id"],
            content=new_content,
            ttl=ttl,
            proxied=proxied,
        )
        await message.answer(
            f"✅ <b>Record Updated Successfully!</b>\n\n{format_record(updated, detailed=True)}",
            parse_mode="HTML",
        )
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


# ============================================================================
# DELETE COMMAND (Single-line with confirmation + Interactive)
# ============================================================================


@router.message(Command("delete"))
async def cmd_delete(message: Message, cf: CloudflareAPI, state: FSMContext) -> None:
    """
    Delete a DNS record.

    Single-line usage:
        /delete <name> [type]

    Examples:
        /delete sub          - Delete if single match
        /delete sub A        - Delete specific type

    Interactive usage:
        /delete    (without arguments)
    """
    if not await require_zone(message, cf):
        return

    args = message.text.split()[1:] if message.text else []

    # Interactive mode
    if not args:
        try:
            records = await cf.list_records()
            if not records:
                await message.answer("❌ No DNS records found.", parse_mode="HTML")
                return

            await state.set_state(DeleteRecordStates.waiting_for_record_selection)
            await message.answer(
                "🗑️ <b>Delete DNS Record</b> (Interactive Mode)\n\n"
                "Select a record to delete:\n\n"
                "<i>Or use single-line command:</i>\n"
                "<code>/delete name [type]</code>",
                parse_mode="HTML",
                reply_markup=get_records_keyboard(records, "delete_select"),
            )
        except CloudflareAPIError as e:
            await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")
        return

    # Single-line mode
    name = args[0]
    record_type = args[1].upper() if len(args) > 1 else None

    try:
        records = await cf.find_records_by_name(name)

        if record_type:
            records = [r for r in records if r.get("type") == record_type]

        if not records:
            msg = f"❌ No record found matching <code>{escape(name)}</code>"
            if record_type:
                msg += f" with type <code>{escape(record_type)}</code>"
            await message.answer(msg, parse_mode="HTML")
            return

        if len(records) > 1:
            # Multiple matches - ask to select
            await message.answer(
                f"⚠️ Found {len(records)} records matching <code>{escape(name)}</code>.\n"
                f"Select which one to delete or specify type:\n"
                f"<code>/delete {escape(name)} TYPE</code>",
                parse_mode="HTML",
                reply_markup=get_records_keyboard(records, "delete_confirm"),
            )
            return

        # Single match - show confirmation
        record = records[0]
        await state.update_data(delete_record_id=record["id"])
        await state.set_state(DeleteRecordStates.confirm)
        await message.answer(
            f"⚠️ <b>Confirm Deletion</b>\n\n"
            f"Are you sure you want to delete this record?\n\n"
            f"{format_record(record, detailed=True)}",
            parse_mode="HTML",
            reply_markup=get_confirm_keyboard("delete", record["id"]),
        )
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


# ============================================================================
# TOGGLE PROXY COMMAND
# ============================================================================


@router.message(Command("toggle_proxy"))
async def cmd_toggle_proxy(message: Message, cf: CloudflareAPI) -> None:
    """
    Toggle the Cloudflare proxy status for a record.

    Usage:
        /toggle_proxy <name>

    Example:
        /toggle_proxy sub.example.com
    """
    if not await require_zone(message, cf):
        return

    args = message.text.split()[1:] if message.text else []

    if not args:
        await message.answer(
            "❌ Usage: /toggle_proxy &lt;name&gt;\n"
            "Example: /toggle_proxy sub.example.com",
            parse_mode="HTML",
        )
        return

    name = args[0]

    try:
        records = await cf.find_records_by_name(name)
        # Filter to only proxyable types
        records = [r for r in records if r.get("type") in ("A", "AAAA", "CNAME")]

        if not records:
            await message.answer(
                f"❌ No proxyable record found matching <code>{escape(name)}</code>\n"
                "(Only A, AAAA, and CNAME records can be proxied)",
                parse_mode="HTML",
            )
            return

        if len(records) > 1:
            await message.answer(
                f"⚠️ Found {len(records)} proxyable records matching <code>{escape(name)}</code>.\n"
                "Select which one to toggle:",
                parse_mode="HTML",
                reply_markup=get_records_keyboard(records, "toggle_proxy"),
            )
            return

        record = records[0]
        updated = await cf.toggle_proxy(record["id"])
        new_status = "🟠 Proxied" if updated.get("proxied") else "⚪ DNS Only"

        await message.answer(
            f"✅ <b>Proxy Status Toggled!</b>\n\n"
            f"Record: <code>{escape(updated['name'])}</code>\n"
            f"New status: {new_status}",
            parse_mode="HTML",
        )
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


# ============================================================================
# ZONE COMMANDS
# ============================================================================


@router.message(Command("zones"))
async def cmd_zones(message: Message, cf: CloudflareAPI) -> None:
    """List available Cloudflare zones."""
    try:
        zones = await cf.list_zones()

        if not zones:
            await message.answer("❌ No zones found.", parse_mode="HTML")
            return

        # Show current zone if set
        current_zone = None
        if cf.default_zone_id:
            try:
                current_zone = await cf.get_zone_info()
            except CloudflareAPIError:
                pass

        lines = ["🌐 <b>Available Zones</b>\n"]
        if current_zone:
            lines.append(f"📍 Current: <code>{escape(current_zone.get('name', ''))}</code>\n")

        for zone in zones:
            name = escape(zone.get("name", "Unknown"))
            status = zone.get("status", "unknown")
            is_current = current_zone and zone.get("id") == current_zone.get("id")
            marker = "→ " if is_current else "• "
            lines.append(f"{marker}<code>{name}</code> - {status}")

        lines.append("\n<b>Switch zone:</b>")
        lines.append("• /zone example.com - by domain name")
        await message.answer("\n".join(lines), parse_mode="HTML")
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


@router.message(Command("zone"))
async def cmd_zone(message: Message, cf: CloudflareAPI) -> None:
    """
    Switch to a different zone or show current zone.

    Usage:
        /zone                  - Show current zone
        /zone example.com      - Switch by domain name
        /zone <zone_id>        - Switch by zone ID
    """
    args = message.text.split()[1:] if message.text else []

    if not args:
        # Show current zone
        if not cf.default_zone_id:
            await message.answer(
                "⚠️ <b>No zone selected</b>\n\n"
                "Use /zones to see available domains\n"
                "Then /zone example.com to select one",
                parse_mode="HTML",
            )
            return

        try:
            zone_info = await cf.get_zone_info()
            await message.answer(
                f"🌐 <b>Current Zone</b>\n\n"
                f"Name: <code>{escape(zone_info.get('name', 'Unknown'))}</code>\n"
                f"ID: <code>{escape(zone_info.get('id', 'N/A'))}</code>\n"
                f"Status: {zone_info.get('status', 'unknown')}\n\n"
                "<i>Use /zone domain to switch zones</i>\n"
                "<i>Use /zones to list all zones</i>",
                parse_mode="HTML",
            )
        except CloudflareAPIError as e:
            await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")
        return

    # Switch zone - can be zone ID or domain name
    zone_arg = args[0]

    # Check if it looks like a domain name (contains a dot but isn't a UUID)
    if "." in zone_arg and len(zone_arg) < 32:
        # Treat as domain name - find the zone
        try:
            zones = await cf.list_zones()
            matching_zone = None
            for zone in zones:
                if zone.get("name", "").lower() == zone_arg.lower():
                    matching_zone = zone
                    break

            if not matching_zone:
                await message.answer(
                    f"❌ Zone not found: <code>{escape(zone_arg)}</code>\n\n"
                    "Use /zones to see available domains.",
                    parse_mode="HTML",
                )
                return

            cf.default_zone_id = matching_zone["id"]
            await message.answer(
                f"✅ <b>Switched to Zone</b>\n\n"
                f"Name: <code>{escape(matching_zone.get('name', ''))}</code>\n"
                f"ID: <code>{escape(matching_zone.get('id', ''))}</code>",
                parse_mode="HTML",
            )
        except CloudflareAPIError as e:
            await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")
    else:
        # Treat as zone ID
        cf.default_zone_id = zone_arg

        try:
            zone_info = await cf.get_zone_info()
            await message.answer(
                f"✅ <b>Switched to Zone</b>\n\n"
                f"Name: <code>{escape(zone_info.get('name', 'Unknown'))}</code>\n"
                f"ID: <code>{escape(zone_info.get('id', 'N/A'))}</code>",
                parse_mode="HTML",
            )
        except CloudflareAPIError as e:
            cf.default_zone_id = None  # Reset on failure
            await message.answer(
                f"❌ Failed to switch zone: {escape(e.message)}\n"
                "Make sure the zone ID is correct.\n\n"
                "Use /zones to see available domains.",
                parse_mode="HTML",
            )


# ============================================================================
# EXPORT COMMAND
# ============================================================================


@router.message(Command("export"))
async def cmd_export(message: Message, cf: CloudflareAPI) -> None:
    """
    Export DNS records as JSON.

    Usage:
        /export         - Export all records
        /export A       - Export only A records
    """
    if not await require_zone(message, cf):
        return

    args = message.text.split()[1:] if message.text else []
    record_type = args[0].upper() if args else None

    if record_type and record_type not in VALID_RECORD_TYPES:
        await message.answer(
            f"❌ Invalid record type: <code>{escape(record_type)}</code>",
            parse_mode="HTML",
        )
        return

    try:
        records = await cf.export_records(record_type=record_type)

        if not records:
            await message.answer("❌ No records to export.", parse_mode="HTML")
            return

        # Format as JSON
        export_data = []
        for r in records:
            export_data.append({
                "name": r.get("name"),
                "type": r.get("type"),
                "content": r.get("content"),
                "ttl": r.get("ttl"),
                "proxied": r.get("proxied"),
            })

        json_str = json.dumps(export_data, indent=2)

        # Split if too long for a single message
        if len(json_str) > 4000:
            await message.answer(
                f"📦 <b>Export</b> ({len(records)} records)\n\n"
                f"<pre>{escape(json_str[:3900])}\n...(truncated)</pre>",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"📦 <b>Export</b> ({len(records)} records)\n\n"
                f"<pre>{escape(json_str)}</pre>",
                parse_mode="HTML",
            )
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


# ============================================================================
# INTERACTIVE FLOW STATE HANDLERS
# ============================================================================


@router.message(AddRecordStates.waiting_for_name)
async def add_flow_name(message: Message, state: FSMContext) -> None:
    """Handle record name input in add flow."""
    name = message.text.strip() if message.text else ""

    if not name:
        await message.answer("❌ Please enter a valid record name.")
        return

    await state.update_data(name=name)
    await state.set_state(AddRecordStates.waiting_for_type)
    await message.answer(
        f"📝 Record name: <code>{escape(name)}</code>\n\n"
        "Select the record type:",
        parse_mode="HTML",
        reply_markup=get_record_types_keyboard(),
    )


@router.message(AddRecordStates.waiting_for_content)
async def add_flow_content(message: Message, state: FSMContext, cf: CloudflareAPI) -> None:
    """Handle content input in add flow."""
    content = message.text.strip() if message.text else ""

    if not content:
        await message.answer("❌ Please enter valid content.")
        return

    data = await state.get_data()
    name = data.get("name", "")
    record_type = data.get("type", "")
    ttl = data.get("ttl", 1)
    proxied = data.get("proxied", False)

    try:
        record = await cf.create_record(
            name=name,
            record_type=record_type,
            content=content,
            ttl=ttl,
            proxied=proxied,
        )
        await state.clear()
        await message.answer(
            f"✅ <b>Record Created!</b>\n\n{format_record(record, detailed=True)}",
            parse_mode="HTML",
        )
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


@router.message(UpdateRecordStates.waiting_for_new_content)
async def update_flow_content(message: Message, state: FSMContext, cf: CloudflareAPI) -> None:
    """Handle new content input in update flow."""
    content = message.text.strip() if message.text else ""

    if not content:
        await message.answer("❌ Please enter valid content.")
        return

    data = await state.get_data()
    record_id = data.get("record_id", "")

    try:
        updated = await cf.update_record(record_id=record_id, content=content)
        await state.clear()
        await message.answer(
            f"✅ <b>Record Updated!</b>\n\n{format_record(updated, detailed=True)}",
            parse_mode="HTML",
        )
    except CloudflareAPIError as e:
        await message.answer(f"❌ Error: {escape(e.message)}", parse_mode="HTML")


# Cancel handler for any state
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Cancel current operation."""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("❌ Operation cancelled.")
    else:
        await message.answer("ℹ️ No active operation to cancel.")