"""
Emoji picker.

The database is data/emoji.ru.json, built by tools/build_emoji.py. It is a
hand-written table rather than something derived from Python's unicodedata,
because unicodedata only knows English names — 🔥 is "FIRE" — and searching for
"огонь" would find nothing.

Selecting an emoji copies it. It does not type it: wtype is not installed, and
there is no way to synthesise a keystroke into the focused window without it.

Rendering caveat: rofi is configured with an explicit font family, and the
fontconfig rules in ~/.config/fontconfig/fonts.conf only append Noto Color Emoji
to the generic sans-serif/serif/monospace families. Without a matching rule for
the launcher's own font, these rows render as monochrome Font Awesome glyphs or
as tofu. install.sh checks for that rule.
"""
from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

from ..rows import back_row, note_row
from ..strings import t

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "emoji.ru.json"


def load():
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def copy(char):
    subprocess.run(["wl-copy"], input=char.encode("utf-8"), check=False)


def rows():
    result = [back_row(t("back"), t("back_meta"))]
    items = load()
    if not items:
        result.append(note_row(t("emoji_missing")))
        return result

    for item in items:
        char = item["char"]
        name = item["name"]
        result.append((char, {
            "display": f"{char}  {html.escape(name)}",
            # The category is in meta too, so "лица" lists every face at once.
            "meta": f"{name} {item['aliases']} {item['category']}",
            "info": f"emo:{char}",
        }))
    return result
