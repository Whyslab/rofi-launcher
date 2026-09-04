"""
Power actions.

The action list is taken from ~/.config/wlogout/layout so that the hub and the
SUPER+Escape overlay cannot drift apart into two different answers to "what does
'Suspend' do on this machine".

Three of the six are irreversible in the sense that matters here — they throw
away everything unsaved — so they get a confirmation step. Lock, suspend and
hibernate all come back to the same session, so they do not.

The confirmation screen puts "No" first deliberately: it is the row the cursor
lands on, so a reflex Enter cancels rather than shuts the machine down.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..rows import back_row, note_row
from ..strings import t

LAYOUT = Path.home() / ".config/wlogout/layout"

# label → (command, translation key, needs confirmation)
ACTIONS = {
    "lock":      (["loginctl", "lock-session"], "power_lock", False),
    "suspend":   (["systemctl", "suspend"], "power_suspend", False),
    "hibernate": (["systemctl", "hibernate"], "power_hibernate", False),
    "logout":    (["hyprctl", "dispatch", "exit"], "power_logout", True),
    "reboot":    (["systemctl", "reboot"], "power_reboot", True),
    "poweroff":  (["systemctl", "poweroff"], "power_poweroff", True),
}

ORDER = ("lock", "suspend", "hibernate", "logout", "reboot", "poweroff")


def _layout_commands():
    """{label: shell command} from wlogout's layout, if it is readable.

    The file is a stream of JSON objects, one per line, not a JSON array — so it
    is parsed line by line rather than with a single json.load.
    """
    out = {}
    try:
        text = LAYOUT.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        label, action = entry.get("label"), entry.get("action")
        if label and action:
            out[label] = action
    return out


def command_for(label):
    """The shell command wlogout uses, or our own argv if the layout has none.

    wlogout's own `lock` action repaints the wallpaper before locking, which is
    worth keeping — that is exactly the kind of local detail that would be lost
    by hardcoding a list here.
    """
    from_layout = _layout_commands().get(label)
    if from_layout:
        return ["sh", "-c", from_layout]
    argv, _, _ = ACTIONS[label]
    return list(argv)


def needs_confirm(label):
    return ACTIONS[label][2]


def run(label):
    if label not in ACTIONS:
        return
    subprocess.Popen(
        command_for(label),
        start_new_session=True, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def rows():
    result = [back_row(t("back"), t("back_meta"))]
    for label in ORDER:
        _, key, _ = ACTIONS[label]
        result.append((label, {
            "display": t(key),
            "meta": f"{t(key)} {label}",
            "info": f"pw:{label}",
        }))
    return result


def confirm_rows(label):
    """Two rows, "No" first so that a reflex Enter is the safe answer."""
    if label not in ACTIONS:
        return [back_row(t("back"), t("back_meta")), note_row(t("empty"))]
    action = t(ACTIONS[label][1])
    return [
        ("no", {
            "display": t("power_no"),
            "meta": "no нет cancel отмена",
            "info": "up",
            "permanent": "true",
        }),
        ("yes", {
            "display": t("power_yes", action=action),
            "meta": "yes да confirm подтвердить",
            "info": f"pwc:{label}",
        }),
    ]
