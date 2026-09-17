#!/usr/bin/env python3
"""
The animations grid — its own rofi script mode, in its own window.

Separate from the hub for the same reason the wallpaper picker is: this needs a
wide window with large thumbnails, the hub needs a narrow list with small icons,
and rofi will not restyle itself between calls.

  Enter           open a screen, or apply a preset / variant / speed for good
                  (writes config, reloads)
  Ctrl+Alt+Space  preview the selected row live (writes nothing; hyprctl reload
                  undoes it) — a variant or speed shows only its own category
  Escape          leave

Live preview cannot be shown while this window is open: rofi is a layer-shell
surface and any ordinary window opens underneath it. So Ctrl+Alt+Space closes this
window first, and bin/anim-preview.sh reopens it when the demonstration is over.

Debugging without rofi:
  ROFI_RETV=0 ./anim_mode.py | cat -v
"""
from __future__ import annotations

import html
import os
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "rofi_hub"

from .rows import emit_directive, emit_row  # noqa: E402
from .sections import animations  # noqa: E402
from .strings import t  # noqa: E402

RETV_PREVIEW = 10  # kb-custom-1, bound to Ctrl+Alt+Space by bin/hub-animations.sh

PREVIEW_SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "anim-preview.sh"

# Screens, carried in each row's `info` so the next call knows where it is:
#   root            the presets row and one row per category
#   presets         every preset (the grid this window used to be)
#   cat:<category>  speeds, "as in the preset", the variants
# ROFI_ANIM_LEVEL picks the first screen; anim-preview.sh sets it when it reopens
# the window after a demonstration, so the user lands back where they were.


def _rows_for(level):
    if level == "presets":
        return animations.preset_rows(), t("anim_hint")
    if level.startswith("cat:") and level[4:] in animations.CATEGORY_LEAVES:
        return animations.category_rows(level[4:]), t("anim_cat_hint")
    return animations.root_rows(), t("anim_root_hint")


def _prompt_for(level):
    if level.startswith("cat:") and level[4:] in animations.CATEGORY_TITLE:
        return t(animations.CATEGORY_TITLE[level[4:]])
    if level == "presets":
        return t("anim_presets")
    return t("sec_animations")


def render(level="root", message=None, select=None):
    rows, hint = _rows_for(level)
    emit_directive("use-hot-keys", "true")
    emit_directive("markup-rows", "true")
    emit_directive("no-custom", "true")
    emit_directive("prompt", _prompt_for(level))
    emit_directive("message", html.escape(message or hint))

    if select is not None:
        for index, (text, _) in enumerate(rows):
            if text == select:
                emit_directive("keep-selection", "true")
                emit_directive("new-selection", str(index))
                break

    for text, opts in rows:
        emit_row(text, **opts)


def start_preview(*args, level="root", select=""):
    """Hand the demonstration to a detached script and let this window close."""
    if not PREVIEW_SCRIPT.is_file():
        return
    env = dict(os.environ, ROFI_ANIM_LEVEL=level, ROFI_HUB_SELECT=select)
    subprocess.Popen(
        [str(PREVIEW_SCRIPT), *args],
        start_new_session=True, close_fds=True, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _level_of(info):
    """Which screen a row lives on, from its info."""
    if info.startswith("up:"):
        return info[3:]
    if info.startswith("anim:"):
        return "presets"
    if info.startswith(("var:", "speed:")):
        return "cat:" + info.split(":")[1]
    return "root"


def main():
    argv_text = sys.argv[1] if len(sys.argv) > 1 else ""
    retv = int(os.environ.get("ROFI_RETV", "0") or 0)
    info = os.environ.get("ROFI_INFO", "")

    if retv == 1:
        if info == "up" or info.startswith("up:"):
            render("root")
            return
        if info.startswith("nav:"):
            render(info[4:])
            return
        if info.startswith("anim:") or (not info and animations.get(argv_text)):
            preset = animations.get(info[5:] if info else argv_text)
            if preset is None:
                render("presets")
                return
            animations.apply_persistent(preset)
            return  # empty output → rofi closes
        # A category change keeps the window open on the same tile: tuning is
        # trying things one after another. hyprctl reload leaves an open rofi
        # alone (checked on 0.56.2), and a notification says what happened.
        if info.startswith("var:"):
            _, category, vid = info.split(":", 2)
            animations.set_variant(category, None if vid == "-" else vid)
            render(f"cat:{category}", select=argv_text)
            return
        if info.startswith("speed:"):
            _, category, speed = info.split(":", 2)
            animations.set_speed(category, speed)
            render(f"cat:{category}", select=argv_text)
            return
        render("root")
        return

    if retv == RETV_PREVIEW:
        level = _level_of(info)
        if info.startswith("anim:") and animations.get(info[5:]) is not None:
            start_preview(info[5:], level=level, select=argv_text)
            return  # close first; the script reopens this window afterwards
        if info.startswith("var:"):
            _, category, vid = info.split(":", 2)
            start_preview("cat", category, "var", vid, level=level, select=argv_text)
            return
        if info.startswith("speed:"):
            _, category, speed = info.split(":", 2)
            start_preview("cat", category, "speed", speed, level=level, select=argv_text)
            return
        render(level, select=argv_text)  # a navigation row: nothing to show
        return

    render(
        os.environ.get("ROFI_ANIM_LEVEL") or "root",
        select=os.environ.get("ROFI_HUB_SELECT") or None,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit_directive("message", t("error", error=html.escape(str(exc))))
        emit_row(t("error_row"), nonselectable="true")
        sys.exit(0)
