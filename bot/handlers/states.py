"""FSM states for multi-step operations."""

from aiogram.fsm.state import State, StatesGroup


class AddRecordStates(StatesGroup):
    """States for interactive record creation flow."""

    waiting_for_name = State()
    waiting_for_type = State()
    waiting_for_content = State()
    waiting_for_ttl = State()
    waiting_for_proxied = State()
    confirm = State()


class UpdateRecordStates(StatesGroup):
    """States for interactive record update flow."""

    waiting_for_record_selection = State()
    waiting_for_new_content = State()
    waiting_for_ttl = State()
    waiting_for_proxied = State()
    confirm = State()


class DeleteRecordStates(StatesGroup):
    """States for interactive record deletion flow."""

    waiting_for_record_selection = State()
    confirm = State()


class ZoneSelectionStates(StatesGroup):
    """States for zone selection."""

    waiting_for_zone = State()