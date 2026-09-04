#!/usr/bin/env python3
"""
The hub: one rofi script mode covering applications and every section.

Protocol: man rofi-script(5).
  ROFI_RETV=0      — first call
  ROFI_RETV=1      — a row was selected ($1 = its text, ROFI_INFO = its info)
  ROFI_RETV=10..28 — kb-custom-1..19 (needs use-hot-keys=true)
  ROFI_DATA        — the state the script handed to itself last time

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
    GLYPH_SECTION,
    dim,
    emit_directive,
    emit_row,
    separator,
)
from .sections import apps, clipboard, emoji, power, screenshot, wallpaper, windows
from .strings import t

# kb-custom-1..6 arrive as ROFI_RETV 10..15. The first five are the launcher's
# original bindings and keep their meaning; 15 is the hub's "remove this".
RETV_PIN, RETV_UNPIN, RETV_UP, RETV_DOWN, RETV_BACK, RETV_DELETE = 10, 11, 12, 13, 14, 15

# level → (translation key for the title, module drawing it)
SECTIONS = (
    (state.CLIPBOARD, "sec_clipboard", "clip_hint"),
    (state.WINDOWS, "sec_windows", "win_hint"),
    (state.EMOJI, "sec_emoji", "emoji_hint"),
    (state.SCREENSHOT, "sec_screenshot", "shot_hint"),
    (state.POWER, "sec_power", "power_hint"),
)


def _section_row(level, label_key, meta_key, info):
    return (f"go:{level}", {
        "display": f"{dim(GLYPH_SECTION)}  {html.escape(t(label_key))}  {dim(ARROW)}",
        "meta": t(meta_key),
        "info": info,
    })


def build_root(app_index, folders, favorites):
    """Pinned applications, then folders, then the hub's own sections."""
    rows = apps.pinned_rows(app_index, favorites)
    folders_rows = apps.folder_rows(folders)

    if rows and folders_rows:
        rows.append(separator("apps"))
    rows.extend(folders_rows)

    section_rows = [
        _section_row(state.CLIPBOARD, "sec_clipboard", "sec_clipboard_meta",
                     f"go:{state.CLIPBOARD}"),
        ("go:wallpaper", {
            "display": f"{dim(GLYPH_SECTION)}  {html.escape(t('sec_wallpaper'))}  {dim(ARROW)}",
            "meta": t("sec_wallpaper_meta"),
            "info": "run:wallpaper",
        }),
        ("go:animations", {
            "display": f"{dim(GLYPH_SECTION)}  {html.escape(t('sec_animations'))}  {dim(ARROW)}",
            "meta": t("sec_animations_meta"),
            "info": "run:animations",
        }),
        _section_row(state.WINDOWS, "sec_windows", "sec_windows_meta",
                     f"go:{state.WINDOWS}"),
        _section_row(state.EMOJI, "sec_emoji", "sec_emoji_meta", f"go:{state.EMOJI}"),
        _section_row(state.SCREENSHOT, "sec_screenshot", "sec_screenshot_meta",
                     f"go:{state.SCREENSHOT}"),
        _section_row(state.POWER, "sec_power", "sec_power_meta", f"go:{state.POWER}"),
    ]

    if rows or folders_rows:
        rows.append(separator("sections"))
    rows.extend(section_rows)
    return rows


def _section_rows(level, argument):
    if level == state.CLIPBOARD:
        return clipboard.rows()
    if level == state.WINDOWS:
        return windows.rows()
    if level == state.EMOJI:
        return emoji.rows()
    if level == state.SCREENSHOT:
        return screenshot.rows()
    if level == state.POWER:
        return power.confirm_rows(argument) if argument else power.rows()
    return []


def _title_and_hint(level, argument):
    for section_level, label_key, hint_key in SECTIONS:
        if level == section_level:
            if level == state.POWER and argument:
                action = t(power.ACTIONS[argument][1]) if argument in power.ACTIONS else argument
                return t("power_confirm", action=action), t("power_hint")
            return t(label_key), t(hint_key)
    return "", ""


def render(level, argument, app_index, folders, favorites, select_text=None, message=None):
    emit_directive("use-hot-keys", "true")   # without this kb-custom never reaches us
    emit_directive("markup-rows", "true")
    emit_directive("no-custom", "true")
    emit_directive("data", state.encode(level, argument))

    if level == state.APPS:
        emit_directive("prompt", argument)
        rows = apps.build_folder(argument, app_index, folders, favorites)
        hint = t("hint_folder")
    elif level == state.ROOT:
        if GLYPH_SEARCH:
            emit_directive("prompt", GLYPH_SEARCH)
        rows = build_root(app_index, folders, favorites)
        hint = t("hint_root")
    else:
        title, hint = _title_and_hint(level, argument)
        emit_directive("prompt", title)
        rows = _section_rows(level, argument)

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
    if info.startswith(("dir:", "go:", "run:", "clip:", "win:", "emo:", "shot:",
                        "pw:", "pwc:", "anim:")) or info == "up":
        return None
    return argv_text or None


def _handle_selection(info, argv_text, level, argument, app_index, folders, favorites):
    """Returns True when the hub should close (empty output ends rofi)."""
    if info == "up" or argv_text == "..":
        if level == state.APPS:
            render(state.ROOT, "", app_index, folders, favorites,
                   select_text=f"dir:{argument}")
        elif level == state.POWER and argument:
            render(state.POWER, "", app_index, folders, favorites)
        else:
            render(state.ROOT, "", app_index, folders, favorites,
                   select_text=f"go:{level}")
        return False

    if info.startswith("dir:"):
        render(state.APPS, info[4:], app_index, folders, favorites)
        return False

    if info.startswith("go:"):
        render(info[3:], "", app_index, folders, favorites)
        return False

    if info == "run:wallpaper":
        wallpaper.open_picker()
        return True

    if info == "run:animations":
        animations_picker()
        return True

    if info.startswith("clip:"):
        clipboard.copy(info[5:])
        return True

    if info.startswith("win:"):
        windows.focus(info[4:])
        return True

    if info.startswith("emo:"):
        emoji.copy(info[4:])
        return True

    if info.startswith("shot:"):
        screenshot.take(info[5:])
        return True

    if info.startswith("pw:"):
        label = info[3:]
        if power.needs_confirm(label):
            render(state.POWER, label, app_index, folders, favorites)
            return False
        power.run(label)
        return True

    if info.startswith("pwc:"):
        power.run(info[4:])
        return True

    desktop_id = selected_id(info, argv_text)
    if desktop_id and desktop_id in app_index:
        apps.launch(app_index[desktop_id], desktop_id)
        return True

    render(level, argument, app_index, folders, favorites)
    return False


def animations_picker():
    """Open the animations grid in its own rofi window, detached."""
    script = Path(__file__).resolve().parent.parent / "bin" / "hub-animations.sh"
    if not script.is_file():
        return
    subprocess.Popen(
        [str(script)],
        start_new_session=True, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _handle_hotkey(retv, info, argv_text, level, argument, app_index, folders, favorites):
    """Returns True when the hub should close."""
    if retv == RETV_BACK:
        if level == state.APPS:
            render(state.ROOT, "", app_index, folders, favorites,
                   select_text=f"dir:{argument}")
        elif level == state.ROOT:
            render(state.ROOT, "", app_index, folders, favorites)
        else:
            render(state.ROOT, "", app_index, folders, favorites,
                   select_text=f"go:{level}")
        return False

    if retv == RETV_DELETE:
        if level == state.CLIPBOARD and info.startswith("clip:"):
            clipboard.delete(info[5:])
            render(level, argument, app_index, folders, favorites,
                   message=t("clip_deleted"))
            return False
        if level == state.WINDOWS and info.startswith("win:"):
            address = info[4:]
            name = windows.name_of(address)
            windows.close(address)
            render(level, argument, app_index, folders, favorites,
                   message=t("win_closed", name=name))
            return False
        render(level, argument, app_index, folders, favorites)
        return False

    # The pin hotkeys only mean anything where applications are listed.
    if level not in (state.ROOT, state.APPS):
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
