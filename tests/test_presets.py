"""
Animation presets.

Two of these guard bugs that were already found and fixed once elsewhere on this
machine, and that a careless preset could bring straight back:

  * the dissolve plugin reads the animation's progress from the window's alpha,
    which fadeOut drives, while windowsOut drives its geometry. Give them
    different durations and the window freezes in place while its pixels are
    still in the air.

  * plugin:dissolve:key_leak_fix stops a held Escape from being handed to the
    window that gains focus. Without it, closing rofi with Escape knocks Firefox
    out of fullscreen video. It is protection, not decoration, and no preset may
    write it.
"""
import json

import pytest

from rofi_hub import hyprconf
from rofi_hub.sections import animations

PRESETS = sorted(animations.PRESET_DIR.glob("*.json"))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_there_are_presets_to_check():
    assert PRESETS, "data/presets/ is empty — the section would show nothing"


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_every_shipped_preset_is_valid(path):
    animations.validate(load(path))


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_a_preset_never_touches_protected_plugin_keys(path):
    plugin = load(path).get("dissolve") or {}
    assert not set(plugin) & hyprconf.PROTECTED_PLUGIN_KEYS


def test_mismatched_dissolve_durations_are_rejected():
    bad = {
        "id": "bad",
        "animations": {"fadeOut": "1, 20, default", "windowsOut": "1, 8, default"},
        "dissolve": {"enabled": 1},
    }
    with pytest.raises(animations.PresetError, match="freeze"):
        animations.validate(bad)


def test_matching_dissolve_durations_are_accepted():
    good = {
        "id": "good",
        "animations": {"fadeOut": "1, 20, default", "windowsOut": "1, 20, default"},
        "dissolve": {"enabled": 1},
    }
    animations.validate(good)


def test_a_preset_may_not_smuggle_in_the_key_leak_fix():
    sneaky = {
        "id": "sneaky",
        "animations": {"fadeOut": "1, 5, default", "windowsOut": "1, 5, default"},
        "dissolve": {"enabled": 1, "key_leak_fix": 0},
    }
    with pytest.raises(animations.PresetError, match="key_leak_fix"):
        animations.validate(sneaky)


def test_durations_are_free_when_the_plugin_is_off():
    """Without the dissolve plugin there is nothing to keep in step, so a preset
    is allowed to fade and move over different times."""
    animations.validate({
        "id": "no-plugin",
        "animations": {"fadeOut": "1, 9, default", "windowsOut": "1, 3, default"},
        "dissolve": {"enabled": 0},
    })


def test_the_baseline_preset_matches_the_configuration_it_replaced():
    """`dissolve` exists to be the current behaviour written down. If it drifts,
    applying it would quietly change the desktop instead of leaving it alone."""
    preset = load(animations.PRESET_DIR / "dissolve.json")
    assert preset["animations"] == {
        "fadeOut": "1, 20, default",
        "windowsOut": "1, 20, default, popin 100%",
        "fadeLayersOut": "1, 20, default",
        "layersOut": "1, 20, default, popin 100%",
    }
    assert preset["dissolve"] == {
        "enabled": 1, "block_size": 4, "drift": 0.35, "spread": 0.55,
        "wave": 0.55, "rise": 200, "lead": 1.15, "dust_life": 0.35, "layers": 1,
    }
