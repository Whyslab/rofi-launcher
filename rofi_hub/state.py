"""
The navigation state the hub hands to itself through ROFI_DATA.

rofi's script mode is stateless between calls: the only thing that survives is
whatever the script printed as the `data` directive last time. So the current
level has to round-trip through a single string.

The encoding is deliberately flat text rather than JSON. ROFI_DATA travels
through an environment variable and back through _clean(), so it must survive
having no newlines, no NUL and no US in it — a JSON blob with user-supplied
folder names in it would be one escaping bug away from breaking navigation.

    ""                 → the hub menu
    "apps"             → applications, pinned entries only
    "apps*"            → applications, every one of them (Tab toggles)
    "apps:Development" → inside a folder
    "clip"             → clipboard
    "emoji"            → emoji

The folder name is the only free-form part and it always comes last, so a
folder called "Media: everything" survives the round trip intact.
"""
from __future__ import annotations

ROOT = ""
APPS = "apps"
CLIPBOARD = "clip"
EMOJI = "emoji"

# Sections drawn inside this rofi session. Wallpaper and animations are not
# here: they need a grid with large thumbnails, and rofi cannot restyle itself
# mid-session, so they open a window of their own.
SECTION_LEVELS = (APPS, CLIPBOARD, EMOJI)

ALL_APPS = "*"   # the marker that means "not just the pinned ones"


def parse(data):
    """ROFI_DATA → (level, argument). An unknown value degrades to the hub."""
    data = (data or "").strip()
    if not data:
        return ROOT, ""
    if data == APPS + ALL_APPS:
        return APPS, ALL_APPS
    if data.startswith(APPS + ":"):
        return APPS, data[len(APPS) + 1:]
    if data in SECTION_LEVELS:
        return data, ""
    return ROOT, ""


def encode(level, argument=""):
    """(level, argument) → ROFI_DATA."""
    if level == ROOT:
        return ""
    if level == APPS:
        if argument == ALL_APPS:
            return APPS + ALL_APPS
        if argument:
            return f"{APPS}:{argument}"
        return APPS
    return level
