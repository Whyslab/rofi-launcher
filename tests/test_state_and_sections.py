"""
Navigation state and the section rows.

The state string is the only thing that survives between two calls of a rofi
script mode, and it travels through an environment variable. A folder named with
a colon in it must not be able to derail navigation.
"""
import json

import pytest

from rofi_hub import state
from rofi_hub.sections import clipboard, emoji, power, screenshot


@pytest.mark.parametrize("level,argument", [
    (state.ROOT, ""),
    (state.APPS, "Development"),
    (state.APPS, "Media: everything"),   # a colon in a folder name
    (state.APPS, "Всё подряд"),
    (state.CLIPBOARD, ""),
    (state.WINDOWS, ""),
    (state.EMOJI, ""),
    (state.SCREENSHOT, ""),
    (state.POWER, ""),
    (state.POWER, "poweroff"),
])
def test_state_survives_a_round_trip(level, argument):
    assert state.parse(state.encode(level, argument)) == (level, argument)


@pytest.mark.parametrize("junk", ["", "   ", "nonsense", "apps", "power!"])
def test_unknown_state_degrades_to_the_root(junk):
    level, _ = state.parse(junk)
    assert level in (state.ROOT, state.APPS, state.POWER)


def test_a_root_state_is_the_empty_string():
    assert state.encode(state.ROOT) == ""


# ─────────────────────────── sections ───────────────────────────

def test_power_confirmation_puts_the_safe_answer_first():
    """The cursor lands on the first row, so a reflex Enter must cancel."""
    rows = power.confirm_rows("poweroff")
    assert rows[0][1]["info"] == "up"
    assert rows[1][1]["info"] == "pwc:poweroff"


@pytest.mark.parametrize("label", ["logout", "reboot", "poweroff"])
def test_irreversible_actions_ask_first(label):
    assert power.needs_confirm(label)


@pytest.mark.parametrize("label", ["lock", "suspend", "hibernate"])
def test_recoverable_actions_do_not_ask(label):
    assert not power.needs_confirm(label)


def test_every_power_action_has_a_command():
    for label in power.ORDER:
        assert power.command_for(label)


def test_screenshot_offers_exactly_the_modes_the_script_has():
    """Two, because ~/.config/hypr/scripts/screenshot.sh implements area and
    screen and nothing else. A third row here would be a button that lies."""
    assert {mode for mode, _, _ in screenshot.MODES} == {"area", "screen"}


def test_clipboard_splits_on_the_first_tab_only(monkeypatch):
    """A copied line can contain tabs. Splitting on all of them would take the
    wrong entry while still looking plausible."""
    payload = b"42\tgit commit -m\tsomething\n43\tplain\n"

    class Result:
        returncode = 0
        stdout = payload

    monkeypatch.setattr(clipboard, "available", lambda: True)
    monkeypatch.setattr(clipboard, "_run", lambda *a, **k: Result())
    assert clipboard.entries() == [
        ("42", "git commit -m\tsomething"),
        ("43", "plain"),
    ]


def test_clipboard_ignores_lines_with_no_tab(monkeypatch):
    class Result:
        returncode = 0
        stdout = b"not an entry\n7\treal\n"

    monkeypatch.setattr(clipboard, "available", lambda: True)
    monkeypatch.setattr(clipboard, "_run", lambda *a, **k: Result())
    assert clipboard.entries() == [("7", "real")]


# ─────────────────────────── emoji ───────────────────────────

def test_the_emoji_database_is_present_and_searchable_in_russian():
    data = json.loads(emoji.DATA.read_text(encoding="utf-8"))
    assert len(data) > 300
    haystack = {d["char"]: f"{d['name']} {d['aliases']}" for d in data}
    assert "огонь" in haystack["🔥"]
    assert "сердце" in haystack["❤️"]


def test_every_emoji_entry_is_complete_and_unique():
    data = json.loads(emoji.DATA.read_text(encoding="utf-8"))
    seen = set()
    for item in data:
        for field in ("char", "name", "aliases", "category"):
            assert field in item, f"{item.get('char')} has no {field}"
        assert item["char"] not in seen, f"duplicate: {item['char']}"
        seen.add(item["char"])
