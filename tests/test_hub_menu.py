"""
The hub screen and the keys that reach it.

The root is a menu of sections and nothing else. It used to also carry the
pinned applications and the folders, and with eight pins the sections fell below
the fold of a 1080p screen — visible only after scrolling, which is the opposite
of what a hub is for.
"""
import re
from pathlib import Path

import pytest

from rofi_hub import hub, state

REPO = Path(__file__).resolve().parent.parent
HUB_SH = (REPO / "bin" / "hub.sh").read_text(encoding="utf-8")


def test_the_hub_shows_only_sections():
    rows = hub.build_hub()
    assert len(rows) == len(hub.SECTIONS)
    assert all(text.startswith("hub:") for text, _ in rows)


def test_every_section_is_numbered_in_order():
    """The digit is what opens the row, so it has to be on the row."""
    for number, (text, opts) in enumerate(hub.build_hub(), start=1):
        assert f">{number}<" in opts["display"], f"{text} does not show its digit"
        assert str(number) in opts["meta"]


@pytest.mark.parametrize("index,key", list(enumerate(k for k, _, _, _ in hub.SECTIONS)))
def test_a_digit_maps_to_the_section_next_to_it(index, key):
    assert hub._digit_target(index)[0] == key


def test_digits_past_the_last_section_do_nothing():
    assert hub._digit_target(len(hub.SECTIONS)) is None
    assert hub._digit_target(-1) is None


def test_every_digit_a_section_needs_is_actually_bound():
    """A section with no binding is a row that advertises a key that does
    nothing."""
    bound = set(re.findall(r'-kb-custom-\d+\s+"(\d)"', HUB_SH))
    needed = {str(n) for n in range(1, len(hub.SECTIONS) + 1)}
    assert needed <= bound, f"unbound digits: {sorted(needed - bound)}"


def test_tab_is_taken_away_from_rofis_own_binding():
    """rofi binds Tab to kb-element-next by default; without freeing it first,
    rofi refuses to start and shows an error dialog instead of the menu."""
    assert '-kb-element-next ""' in HUB_SH
    assert '-kb-custom-7 "Tab"' in HUB_SH


def test_cyrillic_variants_are_spelled_out_for_letter_keys():
    """rofi resolves a binding by symbol, not by physical key, so Ctrl+P in a
    Cyrillic layout is a different binding entirely."""
    assert "Control+Cyrillic_ze" in HUB_SH     # Ctrl+P
    assert "Control+Cyrillic_che" in HUB_SH    # Ctrl+X


def test_tab_toggles_between_pinned_and_every_application():
    assert state.encode(state.APPS, state.ALL_APPS) != state.encode(state.APPS, "")
    assert state.parse(state.encode(state.APPS, state.ALL_APPS))[1] == state.ALL_APPS


def test_grid_sections_are_the_ones_with_no_level():
    """Wallpaper and animations open their own rofi window; the hub must not try
    to draw them itself."""
    windowed = {key for key, _, _, level in hub.SECTIONS if level is None}
    assert windowed == {"wallpaper", "animations"}
