#!/usr/bin/env python3
"""
The animations grid — its own rofi script mode, in its own window.

Separate from the hub for the same reason the wallpaper picker is: this needs a
wide window with large thumbnails, the hub needs a narrow list with small icons,
and rofi will not restyle itself between calls.

  Enter        apply the preset for good (writes config, reloads)
  Ctrl+Alt+Space  preview it live (writes nothing; hyprctl reload undoes it)
  Escape       leave

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


def render(message=None, select=None):
    emit_directive("use-hot-keys", "true")
    emit_directive("markup-rows", "true")
    emit_directive("no-custom", "true")
    emit_directive("prompt", t("sec_animations"))
    emit_directive("message", html.escape(message or t("anim_hint")))

    rows = animations.rows()[1:]  # the grid has no "back" row; Escape leaves
    if select is not None:
        for index, (text, _) in enumerate(rows):
            if text == select:
                emit_directive("keep-selection", "true")
                emit_directive("new-selection", str(index))
                break

    for text, opts in rows:
        emit_row(text, **opts)


def start_preview(preset_id):
    """Hand the demonstration to a detached script and let this window close."""
    if not PREVIEW_SCRIPT.is_file():
        return
    subprocess.Popen(
        [str(PREVIEW_SCRIPT), preset_id],
        start_new_session=True, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main():
    argv_text = sys.argv[1] if len(sys.argv) > 1 else ""
    retv = int(os.environ.get("ROFI_RETV", "0") or 0)
    info = os.environ.get("ROFI_INFO", "")
    preset_id = info[5:] if info.startswith("anim:") else argv_text

    if retv == 1:
        preset = animations.get(preset_id)
        if preset is None:
            render()
            return
        animations.apply_persistent(preset)
        return  # empty output → rofi closes

    if retv == RETV_PREVIEW:
        if animations.get(preset_id) is not None:
            start_preview(preset_id)
        return  # close first; the script reopens this window afterwards

    render(select=os.environ.get("ROFI_HUB_SELECT") or None)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit_directive("message", t("error", error=html.escape(str(exc))))
        emit_row(t("error_row"), nonselectable="true")
        sys.exit(0)
