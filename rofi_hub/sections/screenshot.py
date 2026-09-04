"""
Screenshots, delegating to the existing ~/.config/hypr/scripts/screenshot.sh.

Two modes and no more, because that is what the script actually implements:
`area` and `screen`. There is no window mode there, and inventing one here
would mean a second, divergent implementation of the same job.

The script must run detached and the hub must be gone before slurp appears:
slurp puts its own layer-shell surface over the screen to take a selection, and
two layer surfaces fighting for the keyboard is the same failure that makes
`pkexec` unusable in a pipeline with rofi.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..rows import back_row, note_row
from ..strings import t

SCRIPT = Path.home() / ".config/hypr/scripts/screenshot.sh"

MODES = (
    ("area", "shot_area", "shot_area_meta"),
    ("screen", "shot_screen", "shot_screen_meta"),
)


def available():
    return SCRIPT.is_file() and os.access(SCRIPT, os.X_OK)


def take(mode):
    """Run detached. The caller must already have closed the hub."""
    if mode not in {m for m, _, _ in MODES}:
        return
    subprocess.Popen(
        [str(SCRIPT), mode],
        start_new_session=True, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def rows():
    result = [back_row(t("back"), t("back_meta"))]
    if not available():
        result.append(note_row(str(SCRIPT)))
        return result
    for mode, label_key, meta_key in MODES:
        result.append((mode, {
            "display": t(label_key),
            "meta": t(meta_key),
            "info": f"shot:{mode}",
        }))
    return result
