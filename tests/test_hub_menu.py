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


# ─── shortcuts: applications with a digit of their own on the hub screen ───

def _app(name):
    return {"name": name, "meta": name.lower(), "icon": "", "terminal": False,
            "exec": name.lower(), "path": f"/x/{name}.desktop", "workdir": ""}


@pytest.fixture
def shortcut_file(tmp_path, monkeypatch):
    path = tmp_path / "hub-shortcuts.list"
    monkeypatch.setattr(hub.apps, "SHORTCUTS_FILE", path)
    return path


def test_no_shortcut_file_leaves_the_hub_as_it_was(shortcut_file):
    app_index = {"timer.desktop": _app("Timer")}
    assert len(hub.build_hub(app_index)) == len(hub.SECTIONS)


def test_shortcuts_follow_the_sections_with_the_next_digits(shortcut_file):
    shortcut_file.write_text("# comment\ntimer.desktop\nnetspeed.desktop\n")
    app_index = {"timer.desktop": _app("Timer"), "netspeed.desktop": _app("Speed")}
    rows = hub.build_hub(app_index)
    extra = rows[len(hub.SECTIONS):]
    assert [text for text, _ in extra] == ["hub:app:timer.desktop", "hub:app:netspeed.desktop"]
    for number, (_, opts) in enumerate(extra, start=len(hub.SECTIONS) + 1):
        assert f">{number}<" in opts["display"]
        assert opts["info"].startswith("app:")
    first = len(hub.SECTIONS)
    assert hub._digit_target(first, app_index) == ("app", "timer.desktop")
    assert hub._digit_target(first + 1, app_index) == ("app", "netspeed.desktop")
    assert hub._digit_target(first + 2, app_index) is None


def test_a_missing_application_is_skipped_and_the_digits_close_up(shortcut_file):
    """Otherwise a row would advertise a key that launches nothing."""
    shortcut_file.write_text("gone.desktop\ntimer.desktop\ntimer.desktop\n")
    app_index = {"timer.desktop": _app("Timer")}
    assert hub.shortcuts(app_index) == ["timer.desktop"]
    assert hub._digit_target(len(hub.SECTIONS), app_index) == ("app", "timer.desktop")


def test_no_more_shortcuts_than_there_are_digits(shortcut_file):
    ids = [f"a{i}.desktop" for i in range(10)]
    shortcut_file.write_text("\n".join(ids))
    app_index = {i: _app(i) for i in ids}
    assert len(hub.shortcuts(app_index)) == hub.MAX_SHORTCUTS
    assert len(hub.SECTIONS) + hub.MAX_SHORTCUTS <= 9


def test_every_shortcut_digit_is_bound():
    bound = set(re.findall(r'-kb-custom-\d+\s+"(\d)"', HUB_SH))
    needed = {str(n) for n in range(1, len(hub.SECTIONS) + hub.MAX_SHORTCUTS + 1)}
    assert needed <= bound, f"unbound digits: {sorted(needed - bound)}"


def test_a_shortcut_digit_launches_and_closes_the_hub(shortcut_file, monkeypatch):
    shortcut_file.write_text("timer.desktop\n")
    app_index = {"timer.desktop": _app("Timer")}
    launched = []
    monkeypatch.setattr(hub.apps, "launch", lambda app, i: launched.append(i))
    retv = hub.RETV_DIGIT + len(hub.SECTIONS)
    closed = hub._handle_hotkey(retv, "", "", state.APPS, "", app_index, [], [])
    assert closed is True and launched == ["timer.desktop"]


def test_enter_on_a_shortcut_row_launches_it(shortcut_file, monkeypatch):
    shortcut_file.write_text("timer.desktop\n")
    app_index = {"timer.desktop": _app("Timer")}
    launched = []
    monkeypatch.setattr(hub.apps, "launch", lambda app, i: launched.append(i))
    closed = hub._handle_selection("app:timer.desktop", "hub:app:timer.desktop",
                                   state.ROOT, "", app_index, [], [])
    assert closed is True and launched == ["timer.desktop"]


# ─── hidden sections ───

@pytest.fixture
def hidden_file(tmp_path, monkeypatch):
    path = tmp_path / "hidden.list"
    monkeypatch.setattr(hub.apps, "HIDDEN_FILE", path)
    return path


def test_hidden_sections_leave_the_screen_and_the_digits_close_up(hidden_file, shortcut_file):
    hidden_file.write_text("clipboard\nwallpaper\n")
    shortcut_file.write_text("timer.desktop\n")
    app_index = {"timer.desktop": _app("Timer")}
    texts = [text for text, _ in hub.build_hub(app_index)]
    assert texts == ["hub:apps", "hub:emoji", "hub:animations", "hub:app:timer.desktop"]
    assert hub._digit_target(1, app_index)[0] == "emoji"
    assert hub._digit_target(2, app_index)[0] == "animations"
    assert hub._digit_target(3, app_index) == ("app", "timer.desktop")
    assert hub._digit_target(4, app_index) is None
    for number, (_, opts) in enumerate(hub.build_hub(app_index), start=1):
        assert f">{number}<" in opts["display"]


def test_an_unknown_hidden_key_changes_nothing(hidden_file):
    hidden_file.write_text("no-such-section\n")
    assert len(hub.build_hub()) == len(hub.SECTIONS)
