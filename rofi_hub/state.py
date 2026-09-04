"""
The navigation state the hub hands to itself through ROFI_DATA.

rofi's script mode is stateless between calls: the only thing that survives is
whatever the script printed as the `data` directive last time. So the current
level has to round-trip through a single string.

The encoding is deliberately flat text rather than JSON. ROFI_DATA travels
through an environment variable and back through _clean(), so it must survive
having no newlines, no NUL and no US in it — a JSON blob with user-supplied
folder names in it would be one escaping bug away from breaking navigation.

    ""                → root
    "apps:Development" → inside an application folder
    "clip"            → clipboard
    "win"             → windows
    "emoji"           → emoji
    "shot"            → screenshot
    "power"           → power
    "power!poweroff"  → power, confirming one irreversible action

The folder name is the only free-form part and it always comes last, so a
folder called "Media: everything" survives the round trip intact.
"""
from __future__ import annotations

ROOT = ""
APPS = "apps"
CLIPBOARD = "clip"
WINDOWS = "win"
EMOJI = "emoji"
SCREENSHOT = "shot"
POWER = "power"

SECTION_LEVELS = (CLIPBOARD, WINDOWS, EMOJI, SCREENSHOT, POWER)


def parse(data):
    """ROFI_DATA → (level, argument). An unknown value degrades to the root."""
    data = (data or "").strip()
    if not data:
        return ROOT, ""
    if data.startswith(APPS + ":"):
        return APPS, data[len(APPS) + 1:]
    if data.startswith(POWER + "!"):
        return POWER, data[len(POWER) + 1:]
    if data in SECTION_LEVELS:
        return data, ""
    return ROOT, ""


def encode(level, argument=""):
    """(level, argument) → ROFI_DATA."""
    if level == ROOT:
        return ""
    if level == APPS:
        return f"{APPS}:{argument}"
    if level == POWER and argument:
        return f"{POWER}!{argument}"
    return level
