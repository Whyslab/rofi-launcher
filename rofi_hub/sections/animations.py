"""
Animation presets.

A preset is one JSON file describing the whole feel of the desktop at once:
window open/close, workspace transitions, layer surfaces, its own bezier curves,
and the hypr-dissolve plugin's parameters. Half a preset is not a look.

Two ways to put one on, and the difference matters:

  live preview   hyprctl keyword …   nothing is written; `hyprctl reload` undoes
                                     it completely (verified: keyword sets
                                     overridden=1, reload puts it back to 0)
  apply          generated file      survives reload and reboot

So previewing cannot damage a configuration, by construction rather than by
being careful.

One invariant is enforced here rather than left to whoever writes a preset: when
the dissolve plugin is on, fadeOut and windowsOut must have the same duration.
The plugin measures the dissolve's progress by the window's alpha, which fadeOut
drives, while windowsOut drives the geometry. Split them and the window freezes
in place while its pixels are still flying.
"""
from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

from .. import hyprconf
from ..rows import MARK_ACTIVE, back_row, dim, note_row
from ..strings import LANG, t

PRESET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "presets"
CFG_DIR = Path.home() / ".config" / "rofi-launcher"
ACTIVE_FILE = CFG_DIR / "animation-preset"
PREVIEW_DIR = Path.home() / ".cache" / "rofi-launcher" / "anim-previews"


class PresetError(ValueError):
    """A preset that would misbehave if applied."""


def _localized(value):
    """A preset's name/description is either a plain string or {lang: string}."""
    if isinstance(value, dict):
        return value.get(LANG) or value.get("en") or next(iter(value.values()), "")
    return str(value or "")


def _duration(spec):
    """The speed field of "1, 20, default, popin 100%"."""
    parts = [p.strip() for p in str(spec).split(",")]
    if len(parts) < 2:
        return None
    try:
        return float(parts[1])
    except ValueError:
        return None


def validate(preset):
    """Raise PresetError if the preset is internally inconsistent."""
    pid = preset.get("id")
    if not pid:
        raise PresetError("preset has no id")

    plugin = preset.get("dissolve") or {}
    if not plugin.get("enabled"):
        return preset

    animations = preset.get("animations") or {}
    fade, windows = _duration(animations.get("fadeOut")), _duration(animations.get("windowsOut"))
    if fade is None or windows is None:
        raise PresetError(
            f'{pid}: dissolve is enabled, so both fadeOut and windowsOut must be set'
        )
    if fade != windows:
        raise PresetError(
            f"{pid}: dissolve is enabled but fadeOut ({fade}) and "
            f"windowsOut ({windows}) differ — the window would freeze mid-flight"
        )

    forbidden = set(plugin) & hyprconf.PROTECTED_PLUGIN_KEYS
    if forbidden:
        raise PresetError(
            f"{pid}: presets must not touch {', '.join(sorted(forbidden))} — "
            "those are protection, not decoration"
        )
    return preset


def load_all():
    """Every valid preset, ordered by the `order` field then by id."""
    out = []
    if not PRESET_DIR.is_dir():
        return out
    for path in sorted(PRESET_DIR.glob("*.json")):
        try:
            preset = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        try:
            validate(preset)
        except PresetError:
            continue
        out.append(preset)
    out.sort(key=lambda p: (p.get("order", 999), p.get("id", "")))
    return out


def get(preset_id):
    for preset in load_all():
        if preset["id"] == preset_id:
            return preset
    return None


def active_id():
    try:
        return ACTIVE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _set_active(preset_id):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ACTIVE_FILE.with_suffix(".tmp")
    tmp.write_text(preset_id + "\n", encoding="utf-8")
    tmp.replace(ACTIVE_FILE)


# ─────────────────────────── applying ───────────────────────────

def _keyword(*args):
    subprocess.run(["hyprctl", "keyword", *args], capture_output=True, check=False)


def apply_live(preset):
    """Put the preset on without writing anything. `hyprctl reload` undoes it."""
    validate(preset)
    for name, points in (preset.get("beziers") or {}).items():
        _keyword("bezier", f"{name}," + ",".join(str(p) for p in points))
    for leaf, spec in (preset.get("animations") or {}).items():
        _keyword("animation", f"{leaf},{spec}")
    for key, value in (preset.get("dissolve") or {}).items():
        if key in hyprconf.PROTECTED_PLUGIN_KEYS:
            continue
        _keyword(f"plugin:dissolve:{key}", str(value))


def revert_live():
    """Throw away everything apply_live did, back to what the config says."""
    subprocess.run(["hyprctl", "reload"], capture_output=True, check=False)


def apply_persistent(preset):
    """Write the preset out and reload. Survives a reboot."""
    validate(preset)
    path = hyprconf.write(preset)
    _set_active(preset["id"])
    subprocess.run(["hyprctl", "reload"], capture_output=True, check=False)
    return path


# ─────────────────────────── rows ───────────────────────────

def preview_path(preset_id):
    return PREVIEW_DIR / f"{preset_id}.png"


def rows():
    result = [back_row(t("back"), t("back_meta"))]
    presets = load_all()
    if not presets:
        result.append(note_row(t("anim_none")))
        return result

    current = active_id()
    for preset in presets:
        pid = preset["id"]
        name = _localized(preset.get("name"))
        label = html.escape(name)
        meta = f"{name} {pid} {_localized(preset.get('description'))}"
        if pid == current:
            label += "  " + dim(MARK_ACTIVE)
            meta += f" {t('anim_active')}"
        opts = {
            "display": label,
            "meta": meta,
            "info": f"anim:{pid}",
        }
        image = preview_path(pid)
        if image.is_file():
            opts["icon"] = str(image)
        result.append((pid, opts))
    return result
