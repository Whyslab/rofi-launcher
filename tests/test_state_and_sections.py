"""
Navigation state and the section rows.

The state string is the only thing that survives between two calls of a rofi
script mode, and it travels through an environment variable. A folder named with
a colon in it must not be able to derail navigation.
"""
import json

import pytest

from rofi_hub import state
from rofi_hub.sections import clipboard, emoji


@pytest.mark.parametrize("level,argument", [
    (state.ROOT, ""),
    (state.APPS, ""),
    (state.APPS, state.ALL_APPS),
    (state.APPS, "Development"),
    (state.APPS, "Media: everything"),   # a colon in a folder name
    (state.APPS, "Всё подряд"),
    (state.CLIPBOARD, ""),
    (state.EMOJI, ""),
])
def test_state_survives_a_round_trip(level, argument):
    assert state.parse(state.encode(level, argument)) == (level, argument)


@pytest.mark.parametrize("junk", ["", "   ", "nonsense", "power", "shot"])
def test_unknown_state_degrades_to_the_hub(junk):
    level, _ = state.parse(junk)
    assert level == state.ROOT


def test_a_folder_starting_with_the_marker_is_still_a_folder():
    """The all-applications view is encoded as "apps*". A folder whose name
    merely starts with "*" must not collide with it.

    A folder named exactly "*" would still be shadowed — that is a known and
    accepted corner, not something this asserts away."""
    assert state.parse(state.encode(state.APPS, "*x")) == (state.APPS, "*x")
    assert state.parse(state.encode(state.APPS, state.ALL_APPS)) == (state.APPS, state.ALL_APPS)


def test_a_root_state_is_the_empty_string():
    assert state.encode(state.ROOT) == ""


# ─────────────────────────── sections ───────────────────────────

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
