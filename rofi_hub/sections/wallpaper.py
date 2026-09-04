"""
Wallpaper picker.

This section deliberately does not reimplement the picker. It hands off to
~/.config/hypr/scripts/wallpaper.sh, which already knows how to pre-generate
thumbnails (rofi unpacking 4K originals on every keystroke is unusably slow) and
how to feed rofi icons through a NUL separator so the captions do not swallow
the paths.

It has to be a separate rofi window: the grid is 780px wide with large
thumbnails, the hub's list is 500px with 24px icons, and rofi cannot restyle
itself mid-session — its theme directive is documented as good only for small
changes like a widget's background colour.

The hub must therefore be gone before the picker appears. Two rofi surfaces at
once fight over the keyboard, and the second one silently refuses input; the
caller closes the hub by printing nothing, and this only ever starts a detached
process.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path.home() / ".config/hypr/scripts/wallpaper.sh"


def available():
    return SCRIPT.is_file() and os.access(SCRIPT, os.X_OK)


def open_picker():
    """Start the picker detached. The caller must close the hub."""
    if not available():
        return
    subprocess.Popen(
        [str(SCRIPT), "pick"],
        start_new_session=True, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
