#!/usr/bin/env python3
"""
The hub: one rofi script mode, a menu of sections and the sections themselves.

Protocol: man rofi-script(5).
  ROFI_RETV=0      — first call
  ROFI_RETV=1      — a row was selected ($1 = its text, ROFI_INFO = its info)
  ROFI_RETV=10..28 — kb-custom-1..19 (needs use-hot-keys=true)
  ROFI_DATA        — the state the script handed to itself last time

The root screen is only the list of sections. It used to also carry the pinned
applications and the folders, which meant that with eight pins the sections
themselves sat below the fold of the screen — present but invisible, which is
the opposite of what a hub is for. Applications are now a section like any
other, reached with 1.

Digits 1..5 jump straight to a section, from anywhere, not just from the root.
The cost is real and worth stating: rofi binds a key for the whole session, so
a digit can no longer be typed into the filter box. In exchange, switching
between sections is one keystroke rather than Escape-and-back.

Two sections are not drawn here — wallpaper and animations. Both need a grid
with large thumbnails, and rofi cannot change its layout mid-session: the theme
directive is documented as only good for small things like a widget's
background colour. They open their own rofi window instead, and this process
exits first so that there is never a moment where two rofi instances are both
holding the keyboard.

Debugging without rofi:
  ROFI_RETV=0 ./hub.py | cat -v
  ROFI_DATA=emoji ROFI_RETV=0 ./hub.py | cat -v
"""
from __future__ import annotations

import contextlib
import html
import locale
import os
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):  # run directly, not imported
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "rofi_hub"

from . import state
from .rows import (
    ARROW,
    GLYPH_SEARCH,
    back_row,
    dim,
    emit_directive,
    emit_row,
    separator,
)
from .sections import apps, clipboard, emoji, wallpaper
from .strings import t

# kb-custom-1..11 arrive as ROFI_RETV 10..20.
RETV_PIN = 10        # Ctrl+P
RETV_UNPIN = 11      # unbound by default
RETV_UP = 12         # Ctrl+Alt+Up
RETV_DOWN = 13       # Ctrl+Alt+Down
RETV_BACK = 14       # Alt+Left
RETV_DELETE = 15     # Ctrl+X
RETV_TAB = 16        # Tab
RETV_DIGIT = 17      # 1 .. 5 occupy 17..21

# The order here is the order on the hub screen and the digit that opens each
# one. Adding a section means adding a line here and a binding in bin/hub.sh.
#
# "window" entries are not drawn by this process at all: choosing one closes the
# hub and opens a separate rofi with its own theme.
SECTIONS = (
    ("apps",       "sec_apps",       "sec_apps_meta",       state.APPS),
    ("clipboard",  "sec_clipboard",  "sec_clipboard_meta",  state.CLIPBOARD),
    ("emoji",      "sec_emoji",      "sec_emoji_meta",      state.EMOJI),
    ("wallpaper",  "sec_wallpaper",  "sec_wallpaper_meta",  None),
    ("animations", "sec_animations", "sec_animations_meta", None),
)


def _digit_target(index):
    """Which section digit `index` (0-based) opens, or None."""
    if 0 <= index < len(SECTIONS):
        return SECTIONS[index]
    return None


def build_hub():
    rows = []
    for number, (key, label_key, meta_key, level) in enumerate(SECTIONS, start=1):
        info = f"go:{level}" if level is not None else f"run:{key}"
        rows.append((f"hub:{key}", {
            # The number is part of the label, not decoration: it is the key
            # that opens the row, so it has to be visible on the row.
            "display": f"{dim(str(number))}   {html.escape(t(label_key))}   {dim(ARROW)}",
            "meta": f"{t(meta_key)} {number}",
            "info": info,
        }))
    return rows


def _section_rows(level, argument, app_index, folders, favorites):
    if level == state.APPS:
        if argument == state.ALL_APPS:
            return apps.all_rows(app_index, favorites)
        if argument:
            return apps.build_folder(argument, app_index, folders, favorites)
        return _apps_pinned_rows(app_index, folders, favorites)
    if level == state.CLIPBOARD:
        return clipboard.rows()
    if level == state.EMOJI:
        return emoji.rows()
    return []


def _apps_pinned_rows(app_index, folders, favorites):
    """The applications section as it opens: pinned first, folders under them."""
    rows = [back_row(t("back"), t("back_meta"))]
    rows.extend(apps.pinned_rows(app_index, favorites))
    folder_rows = apps.folder_rows(folders)
    if folder_rows:
        rows.append(separator("apps"))
        rows.extend(folder_rows)
    return rows


def _title_and_hint(level, argument):
    if level == state.APPS:
        if argument == state.ALL_APPS:
            return t("all_apps"), t("hint_apps_all")
        if argument:
            return argument, t("hint_folder")
        return t("sec_apps"), t("hint_apps_pinned")
    if level == state.CLIPBOARD:
        return t("sec_clipboard"), t("clip_hint")
    if level == state.EMOJI:
        return t("sec_emoji"), t("emoji_hint")
    return "", ""


def render(level, argument, app_index, folders, favorites, select_text=None, message=None):
    emit_directive("use-hot-keys", "true")   # without this kb-custom never reaches us
    emit_directive("markup-rows", "true")
    emit_directive("no-custom", "true")
    emit_directive("data", state.encode(level, argument))

    if level == state.ROOT:
        if GLYPH_SEARCH:
            emit_directive("prompt", GLYPH_SEARCH)
        rows = build_hub()
        hint = t("hint_hub")
    else:
        title, hint = _title_and_hint(level, argument)
        emit_directive("prompt", title)
        rows = _section_rows(level, argument, app_index, folders, favorites)

    emit_directive("message", dim(html.escape(message or hint)))

    if select_text is not None:
        for index, (text, _) in enumerate(rows):
            if text == select_text:
                emit_directive("keep-selection", "true")
                emit_directive("new-selection", str(index))
                break

    for text, opts in rows:
        emit_row(text, **opts)


def selected_id(info, argv_text):
    """info is more reliable, but is not guaranteed on kb-custom — then the
    row's own text is the identifier."""
    if info.startswith("app:"):
        return info[4:]
    if info.startswith(("dir:", "go:", "run:", "hub:", "clip:", "emo:")) or info == "up":
        return None
    return argv_text or None


def _open_window(script_name):
    """Open one of the grid sections in its own rofi, detached."""
    script = Path(__file__).resolve().parent.parent / "bin" / script_name
    if not script.is_file():
        return
    subprocess.Popen(
        [str(script)],
        start_new_session=True, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _open_grid_section(key):
    """Wallpaper and animations both open a window of their own; this is the one
    place that knows which script each of them is."""
    if key == "wallpaper":
        wallpaper.open_picker()
    elif key == "animations":
        _open_window("hub-animations.sh")


def _handle_selection(info, argv_text, level, argument, app_index, folders, favorites):
    """Returns True when the hub should close (empty output ends rofi)."""
    if info == "up" or argv_text == "..":
        # Inside a folder or the all-applications list, "back" means back to the
        # applications section, not all the way out to the hub.
        if level == state.APPS and argument:
            render(state.APPS, "", app_index, folders, favorites,
                   select_text=f"dir:{argument}" if argument != state.ALL_APPS else None)
        else:
            render(state.ROOT, "", app_index, folders, favorites,
                   select_text=f"hub:{_key_for_level(level)}")
        return False

    if info.startswith("dir:"):
        render(state.APPS, info[4:], app_index, folders, favorites)
        return False

    if info.startswith("go:"):
        render(info[3:], "", app_index, folders, favorites)
        return False

    if info.startswith("run:"):
        _open_grid_section(info[4:])
        return True

    if info.startswith("clip:"):
        clipboard.copy(info[5:])
        return True

    if info.startswith("emo:"):
        emoji.copy(info[4:])
        return True

    desktop_id = selected_id(info, argv_text)
    if desktop_id and desktop_id in app_index:
        apps.launch(app_index[desktop_id], desktop_id)
        return True

    render(level, argument, app_index, folders, favorites)
    return False


def _key_for_level(level):
    for key, _, _, section_level in SECTIONS:
        if section_level == level:
            return key
    return "apps"


def _handle_hotkey(retv, info, argv_text, level, argument, app_index, folders, favorites):
    """Returns True when the hub should close."""
    if RETV_DIGIT <= retv < RETV_DIGIT + len(SECTIONS):
        section = _digit_target(retv - RETV_DIGIT)
        if section is None:
            render(level, argument, app_index, folders, favorites)
            return False
        key, _, _, section_level = section
        if section_level is None:
            _open_grid_section(key)
            return True
        render(section_level, "", app_index, folders, favorites)
        return False

    if retv == RETV_TAB:
        # Only the applications section has anything to toggle.
        if level == state.APPS:
            new_argument = "" if argument == state.ALL_APPS else state.ALL_APPS
            render(state.APPS, new_argument, app_index, folders, favorites)
        else:
            render(level, argument, app_index, folders, favorites)
        return False

    if retv == RETV_BACK:
        if level == state.APPS and argument:
            render(state.APPS, "", app_index, folders, favorites)
        else:
            render(state.ROOT, "", app_index, folders, favorites,
                   select_text=f"hub:{_key_for_level(level)}")
        return False

    if retv == RETV_DELETE:
        if level == state.CLIPBOARD and info.startswith("clip:"):
            clipboard.delete(info[5:])
            render(level, argument, app_index, folders, favorites,
                   message=t("clip_deleted"))
            return False
        render(level, argument, app_index, folders, favorites)
        return False

    # The pin hotkeys only mean anything where applications are listed.
    if level != state.APPS:
        render(level, argument, app_index, folders, favorites)
        return False

    desktop_id = selected_id(info, argv_text)
    message = None
    if retv == RETV_PIN:
        favorites, message = apps.hotkey_pin(desktop_id, app_index, favorites)
    elif retv == RETV_UNPIN:
        favorites, message = apps.hotkey_unpin(desktop_id, app_index, favorites)
    elif retv == RETV_UP:
        favorites, message = apps.hotkey_move(desktop_id, favorites, -1)
    elif retv == RETV_DOWN:
        favorites, message = apps.hotkey_move(desktop_id, favorites, +1)
    render(level, argument, app_index, folders, favorites,
           select_text=desktop_id, message=message)
    return False


def main():
    with contextlib.suppress(locale.Error):
        locale.setlocale(locale.LC_COLLATE, "")

    argv_text = sys.argv[1] if len(sys.argv) > 1 else ""

    if os.environ.get("ROFI_LAUNCHER_DEBUG"):
        try:
            apps.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(apps.CACHE_DIR / "debug.log", "a", encoding="utf-8") as fh:
                fh.write("RETV={!r} INFO={!r} DATA={!r} argv={!r}\n".format(
                    os.environ.get("ROFI_RETV"), os.environ.get("ROFI_INFO"),
                    os.environ.get("ROFI_DATA"), sys.argv[1:]))
        except OSError:
            pass

    # Manual modes for debugging, outside rofi.
    if argv_text == "--dump-apps":
        app_index = apps.scan_apps()
        for desktop_id in sorted(app_index):
            print(f"{desktop_id:<44} {app_index[desktop_id]['name']}")
        print(f"\ntotal: {len(app_index)}")
        return
    if argv_text == "--launch":
        app_index = apps.scan_apps()
        apps.launch(app_index[sys.argv[2]], sys.argv[2])
        return

    retv = int(os.environ.get("ROFI_RETV", "0") or 0)
    info = os.environ.get("ROFI_INFO", "")
    level, argument = state.parse(os.environ.get("ROFI_DATA", ""))

    app_index = apps.scan_apps()
    folders = apps.load_folders()
    favorites = apps.read_favorites()

    if retv == 1:
        _handle_selection(info, argv_text, level, argument, app_index, folders, favorites)
        return
    if retv >= 10:
        _handle_hotkey(retv, info, argv_text, level, argument,
                       app_index, folders, favorites)
        return

    render(level, argument, app_index, folders, favorites)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # otherwise any bug looks like a successful launch
        emit_directive("message", t("error", error=html.escape(str(exc))))
        emit_row(t("error_row"), nonselectable="true")
        sys.exit(0)
