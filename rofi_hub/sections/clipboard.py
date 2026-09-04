"""
Clipboard history, backed by cliphist.

`cliphist list` prints one entry per line as "<id>\\t<preview>". The split is on
the FIRST tab only: a copied line that itself contains tabs (indented code, a
pasted table row) would otherwise lose everything after its second tab, and the
id would still look plausible — a silent wrong-entry bug rather than a crash.

Binary entries are stored by cliphist as a placeholder line that names the type
and size instead of the content. They are shown as-is rather than hidden: an
image in the history is worth seeing, and selecting it still puts the real bytes
back on the clipboard.
"""
from __future__ import annotations

import html
import shutil
import subprocess

from ..rows import back_row, note_row
from ..strings import t

# cliphist's own placeholder for non-text content, e.g.
# "[[ binary data 2.3 MiB png 1920x1080 ]]"
BINARY_MARK = "[[ binary data"


def available():
    return shutil.which("cliphist") is not None


def _run(args, stdin=None):
    return subprocess.run(
        ["cliphist", *args],
        input=stdin,
        capture_output=True,
        check=False,
    )


def entries(limit=200):
    """[(id, preview)] newest first, exactly as cliphist orders them."""
    if not available():
        return []
    proc = _run(["list"])
    if proc.returncode != 0:
        return []
    out = []
    for raw in proc.stdout.decode("utf-8", "replace").splitlines():
        if not raw.strip():
            continue
        entry_id, _, preview = raw.partition("\t")
        if not _:  # a line with no tab at all is not a cliphist entry
            continue
        out.append((entry_id, preview))
        if len(out) >= limit:
            break
    return out


def copy(entry_id):
    """Put one entry back on the clipboard, bytes intact."""
    decoded = _run(["decode"], stdin=f"{entry_id}\t".encode())
    if decoded.returncode != 0:
        return False
    subprocess.run(["wl-copy"], input=decoded.stdout, check=False)
    return True


def delete(entry_id):
    _run(["delete"], stdin=f"{entry_id}\t".encode())


def _label(preview):
    if preview.startswith(BINARY_MARK):
        return preview.strip()
    return preview


def rows():
    result = [back_row(t("back"), t("back_meta"))]
    if not available():
        result.append(note_row(t("clip_unavailable")))
        return result

    items = entries()
    if not items:
        result.append(note_row(t("clip_empty")))
        return result

    for entry_id, preview in items:
        label = _label(preview)
        result.append((entry_id, {
            "display": html.escape(label),
            "meta": label,
            "info": f"clip:{entry_id}",
        }))
    return result
