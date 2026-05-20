"""Tests for the pure helpers in const.py."""

from custom_components.harvest_right.const import (
    DF_DEHYDRATE,
    DF_EXTRA_DRY,
    DF_VAC_FREEZE,
    STATE_OPTIONS,
    get_drying_state,
)


def test_get_drying_state_dehydrate_takes_priority() -> None:
    """The dehydrate bit wins even when other bits are set."""
    assert get_drying_state(5, DF_DEHYDRATE | DF_EXTRA_DRY) == "Dehydrating"


def test_get_drying_state_extra_dry() -> None:
    """The extra-dry bit maps to the Extra Dry Time label."""
    assert get_drying_state(6, DF_EXTRA_DRY) == "Extra Dry Time"


def test_get_drying_state_default_screen_label() -> None:
    """With no special bit, the screen label is used."""
    assert get_drying_state(5, 0) == "Drying (Heating)"
    assert get_drying_state(6, DF_VAC_FREEZE) == "Drying (Max Temp)"


def test_get_drying_state_unmapped_screen_falls_back_to_drying() -> None:
    """An unmapped drying screen falls back to the bare 'Drying' label."""
    assert get_drying_state(999, 0) == "Drying"


def test_state_options_cover_drying_fallback() -> None:
    """Every value get_drying_state can return is a valid ENUM option."""
    for value in ("Drying", "Extra Dry Time", "Dehydrating", "Unknown"):
        assert value in STATE_OPTIONS


def test_state_options_have_no_duplicates() -> None:
    """The ENUM option list must not contain duplicates."""
    assert len(STATE_OPTIONS) == len(set(STATE_OPTIONS))
