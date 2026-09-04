"""
Open windows, via hyprctl.

Not rofi's built-in `window` mode: rofi 2.0 can drive
zwlr_foreign_toplevel_management_v1, but that is a separate built-in mode which
a script mode cannot enter, and it does not know which workspace a window is on.

Windows are addressed by their hyprctl `address`, never by title. Two terminals
with the same title are the normal case, not the exception, and focusing "the
first one whose title matches" would pick the wrong one about half the time.
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess

from ..rows import back_row, note_row
from ..strings import t


def available():
    return shutil.which("hyprctl") is not None


def _hyprctl_json(args):
    if not available():
        return None
    proc = subprocess.run(
        ["hyprctl", "-j", *args], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def _dispatch(*args):
    subprocess.run(["hyprctl", "dispatch", *args], capture_output=True, check=False)


def clients():
    """Mapped windows, ordered by workspace then by title."""
    data = _hyprctl_json(["clients"]) or []
    out = []
    for c in data:
        if not c.get("mapped", True) or not c.get("address"):
            continue
        ws = c.get("workspace") or {}
        out.append({
            "address": c["address"],
            "class": c.get("class", ""),
            "title": c.get("title", ""),
            "ws_id": ws.get("id", 0),
            "ws_name": ws.get("name", ""),
        })
    # A special workspace has a negative id; sorting on it puts scratchpads last
    # rather than in front of workspace 1.
    out.sort(key=lambda c: (c["ws_id"] < 0, c["ws_id"], c["title"].casefold()))
    return out


def focus(address):
    _dispatch("focuswindow", f"address:{address}")


def close(address):
    _dispatch("closewindow", f"address:{address}")


def _badge(client):
    if client["ws_name"].startswith("special:"):
        return t("win_special")
    return str(client["ws_id"])


def rows():
    result = [back_row(t("back"), t("back_meta"))]
    items = clients()
    if not items:
        result.append(note_row(t("win_empty")))
        return result

    for c in items:
        badge = _badge(c)
        title = c["title"] or c["class"]
        label = f"[{html.escape(badge)}]  {html.escape(c['class'])} — {html.escape(title)}"
        result.append((c["address"], {
            "display": label,
            "meta": f"{c['class']} {title} {badge}",
            "info": f"win:{c['address']}",
        }))
    return result


def name_of(address):
    for c in clients():
        if c["address"] == address:
            return c["title"] or c["class"]
    return address
