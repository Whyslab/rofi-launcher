"""
Animation categories: window open, window close, workspaces, menus.

A category replaces one part of the active preset with a variant, and each has
a speed. The rules worth guarding are the ones that break the desktop quietly:

  * a variant must only touch the leaves its category owns, or choosing "Slide"
    for workspaces could change how windows close;
  * with the dissolve plugin on, the fade and the geometry of a closing surface
    must last exactly as long as each other — speeds included — or the window
    freezes mid-flight;
  * menus can only dissolve while windows do (the plugin cannot dissolve menus
    alone), and when that stops holding they must not be left with the long
    2-second fade that only made sense with particles;
  * nothing tuned should change the desktop while every category is left
    "as in the preset" at normal speed.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rofi_hub import anim_mode, hyprconf
from rofi_hub.sections import animations as a

REPO = Path(__file__).resolve().parent.parent
VARIANT_FILES = sorted((REPO / "data" / "animations").glob("*/*.json"))
PRESET_IDS = [p.stem for p in sorted(a.PRESET_DIR.glob("*.json"))]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def tuning(overrides=None, speed=None):
    return {"overrides": dict(overrides or {}), "speed": dict(speed or {})}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Point the saved state at a temporary directory."""
    monkeypatch.setattr(a, "CFG_DIR", tmp_path)
    monkeypatch.setattr(a, "ACTIVE_FILE", tmp_path / "animation-preset")
    monkeypatch.setattr(a, "TUNING_FILE", tmp_path / "animation-tuning.json")
    return tmp_path


@pytest.fixture
def quiet(monkeypatch):
    """No hyprctl, no notifications, no generated files: record instead."""
    calls = {"written": [], "notified": [], "run": []}
    monkeypatch.setattr(hyprconf, "write", lambda preset: calls["written"].append(preset))
    monkeypatch.setattr(a, "notify", lambda text: calls["notified"].append(text))
    monkeypatch.setattr(a.subprocess, "run", lambda *args, **kw: calls["run"].append(args))
    return calls


# ─────────────────────────── the shipped variants ───────────────────────────

def test_every_category_has_variants():
    for category in a.CATEGORIES:
        assert len(a.load_variants(category)) >= 5, category


@pytest.mark.parametrize("path", VARIANT_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_every_shipped_variant_is_valid(path):
    variant = load(path)
    assert variant["category"] == path.parent.name
    assert variant["id"] == path.stem
    a.validate_variant(variant)


def test_no_variant_is_silently_skipped():
    """load_variants drops invalid files quietly — so count them against disk."""
    for category in a.CATEGORIES:
        on_disk = len(list((a.VARIANT_DIR / category).glob("*.json")))
        assert len(a.load_variants(category)) == on_disk, category


def test_a_variant_may_not_touch_another_categorys_leaves():
    bad = load(a.VARIANT_DIR / "open" / "pop.json")
    bad["animations"]["workspaces"] = "1, 5, o_snap, slide"
    with pytest.raises(a.PresetError, match="does not own"):
        a.validate_variant(bad)


def test_a_variant_curve_must_carry_its_category_prefix():
    bad = load(a.VARIANT_DIR / "workspaces" / "slide.json")
    bad["beziers"] = {"ease": [0.25, 0.1, 0.25, 1.0]}
    with pytest.raises(a.PresetError, match="must start with"):
        a.validate_variant(bad)


def test_a_dissolving_close_variant_needs_equal_durations():
    bad = load(a.VARIANT_DIR / "close" / "dissolve.json")
    bad["animations"]["fadeOut"] = "1, 10, default"
    with pytest.raises(a.PresetError, match="freeze"):
        a.validate_variant(bad)


@pytest.mark.parametrize("key", ["key_leak_fix", "layers"])
def test_a_close_variant_may_not_set_protection_or_the_menu_flag(key):
    bad = load(a.VARIANT_DIR / "close" / "dissolve.json")
    bad["dissolve"][key] = 1
    with pytest.raises(a.PresetError):
        a.validate_variant(bad)


def test_only_close_may_configure_the_plugin():
    bad = load(a.VARIANT_DIR / "layers" / "fade.json")
    bad["dissolve"] = {"enabled": 1}
    with pytest.raises(a.PresetError, match="only window close"):
        a.validate_variant(bad)


# ─────────────────────────── compose ───────────────────────────

@pytest.mark.parametrize("preset_id", PRESET_IDS)
def test_an_untuned_preset_composes_to_itself(preset_id):
    preset = a.get(preset_id)
    composed = a.compose(preset, a.empty_tuning())
    assert composed["animations"] == preset["animations"]
    assert composed["beziers"] == (preset.get("beziers") or {})
    original = preset.get("dissolve") or {}
    if original.get("enabled"):
        assert composed["dissolve"] == {**original, "layers": original.get("layers", 1)}
    else:
        assert composed["dissolve"] == {"enabled": 0}


def test_a_category_replaces_only_its_own_leaves():
    preset = a.get("cinema")
    composed = a.compose(preset, tuning({"workspaces": "fade"}))
    for leaf in ("windowsIn", "windowsOut", "fadeIn", "fadeOut", "layersIn", "layersOut"):
        assert composed["animations"][leaf] == preset["animations"][leaf]
    assert composed["animations"]["workspaces"] == "1, 5, w_ease, fade"
    assert composed["animations"]["specialWorkspace"] == "1, 5, w_ease, fade"


def test_a_leftover_child_leaf_of_the_preset_is_removed():
    preset = json.loads(json.dumps(a.get("slide")))
    preset["animations"]["specialWorkspaceIn"] = "1, 9, ease, fade"
    composed = a.compose(preset, tuning({"workspaces": "vertical"}))
    assert "specialWorkspaceIn" not in composed["animations"]


@pytest.mark.parametrize("preset_id", PRESET_IDS)
@pytest.mark.parametrize("close", [v["id"] for v in a.load_variants("close")] + [None])
@pytest.mark.parametrize("menus", ["dissolve", "fade", None])
@pytest.mark.parametrize("speed", ["fast", "slow"])
def test_every_combination_composes_into_a_valid_config(preset_id, close, menus, speed):
    overrides = {}
    if close:
        overrides["close"] = close
    if menus:
        overrides["layers"] = menus
    composed = a.compose(
        a.get(preset_id), tuning(overrides, {"close": speed, "layers": speed, "open": speed})
    )
    a.validate(composed)
    plugin = composed["dissolve"]
    if plugin.get("enabled") and plugin.get("layers"):
        anims = composed["animations"]
        assert a._duration(anims["fadeLayersOut"]) == a._duration(anims["layersOut"])


def test_menus_cannot_dissolve_without_windows_and_fall_back_to_a_fade():
    composed = a.compose(a.get("slide"), tuning({"layers": "dissolve"}))
    fade = a.get_variant("layers", "fade")
    for leaf, spec in fade["animations"].items():
        assert composed["animations"][leaf] == spec
    assert composed["dissolve"] == {"enabled": 0}


def test_a_dissolve_preset_with_non_dissolving_close_drops_the_slow_menu_fade():
    """The dissolve preset's menus last 2 s because they were meant to dissolve.
    Without the plugin that would be a 2-second fade on every rofi close."""
    composed = a.compose(a.get("dissolve"), tuning({"close": "shrink"}))
    assert composed["dissolve"] == {"enabled": 0}
    assert a._duration(composed["animations"]["layersOut"]) == 3


def test_window_dissolve_alone_leaves_menus_alone():
    composed = a.compose(a.get("slide"), tuning({"close": "dust"}))
    assert composed["dissolve"]["enabled"] == 1
    assert composed["dissolve"]["layers"] == 0
    assert composed["animations"]["layersOut"] == a.get("slide")["animations"]["layersOut"]


def test_menus_dissolve_when_both_are_chosen():
    composed = a.compose(a.get("slide"), tuning({"close": "blast", "layers": "dissolve"}))
    assert composed["dissolve"]["layers"] == 1


def test_menus_can_be_kept_from_dissolving_under_a_dissolve_preset():
    composed = a.compose(a.get("dissolve"), tuning({"layers": "slide"}))
    assert composed["dissolve"]["enabled"] == 1
    assert composed["dissolve"]["layers"] == 0


# ─────────────────────────── speed ───────────────────────────

@pytest.mark.parametrize(("spec", "factor", "expected"), [
    ("1, 20, default, popin 100%", 0.6, "1, 12, default, popin 100%"),
    ("1, 4, c_ease", 1.6, "1, 6.4, c_ease"),
    ("1, 3, o_snap", 0.6, "1, 1.8, o_snap"),
    ("1, 0.6, x", 0.6, "1, 0.5, x"),       # floored, never zero
    ("0", 0.6, "0"),                       # disabled stays disabled
    ("1, 5, ease, slide", 1.0, "1, 5, ease, slide"),
])
def test_scale_spec(spec, factor, expected):
    assert a.scale_spec(spec, factor) == expected


def test_speed_keeps_dissolve_durations_equal():
    composed = a.compose(a.get("dissolve"), tuning(speed={"close": "fast"}))
    assert composed["animations"]["fadeOut"] == "1, 12, default"
    assert composed["animations"]["windowsOut"] == "1, 12, default, popin 100%"


def test_speed_on_an_inherited_category_writes_hyprlands_default_scaled():
    """The dissolve preset does not set window open at all, so Hyprland falls
    back to `global` (1, 8, default). A speed has to materialise that first."""
    composed = a.compose(a.get("dissolve"), tuning(speed={"open": "slow"}))
    assert composed["animations"]["windowsIn"] == "1, 12.8, default"
    assert composed["animations"]["fadeIn"] == "1, 12.8, default"


def test_speed_touches_only_its_category():
    preset = a.get("slide")
    composed = a.compose(preset, tuning(speed={"workspaces": "fast"}))
    assert composed["animations"]["windowsIn"] == preset["animations"]["windowsIn"]
    assert composed["animations"]["workspaces"] == "1, 3, ease, slide"


def test_speed_on_the_instant_preset_changes_nothing():
    composed = a.compose(a.get("instant"), tuning(speed={"open": "slow"}))
    assert composed["animations"]["windowsIn"] == "0"


@pytest.mark.parametrize("fmt", ["conf", "lua"])
def test_fractional_speeds_render_in_both_formats(fmt):
    composed = a.compose(a.get("slide"), tuning(speed={"open": "slow"}))
    text = hyprconf.render(composed, fmt)
    assert ("speed = 6.4" if fmt == "lua" else "windowsIn, 1, 6.4, ease, slide") in text


# ─────────────────────────── saved tuning ───────────────────────────

def test_missing_tuning_is_empty(cfg):
    assert a.load_tuning() == a.empty_tuning()


@pytest.mark.parametrize("junk", [
    "not json", "[]", '{"overrides": 5}', '{"speed": ["fast"]}', '{"speed": {"open": [1]}}', "",
])
def test_broken_tuning_is_ignored(cfg, junk):
    a.TUNING_FILE.write_text(junk, encoding="utf-8")
    assert a.load_tuning() == a.empty_tuning()


def test_unknown_entries_are_dropped(cfg):
    a.TUNING_FILE.write_text(json.dumps({
        "overrides": {"open": "spring", "close": "gone-in-an-update", "colour": "red"},
        "speed": {"open": "fast", "close": "ludicrous", "layers": "normal"},
    }), encoding="utf-8")
    assert a.load_tuning() == tuning({"open": "spring"}, {"open": "fast"})


def test_tuning_round_trips(cfg):
    saved = tuning({"close": "sand"}, {"workspaces": "slow"})
    a.save_tuning(saved)
    assert a.load_tuning() == saved


def test_applying_a_preset_drops_the_tuning(cfg, quiet):
    a.save_tuning(tuning({"close": "blast"}, {"open": "fast"}))
    a.apply_persistent(a.get("slide"))
    assert a.load_tuning() == a.empty_tuning()
    assert quiet["written"][-1]["dissolve"] == {"enabled": 0}
    assert a.active_id() == "slide"


def test_set_variant_writes_the_composed_config(cfg, quiet):
    a._set_active("dissolve")
    a.set_variant("open", "spring")
    assert a.load_tuning()["overrides"] == {"open": "spring"}
    assert quiet["written"][-1]["animations"]["windowsIn"] == "1, 5, o_spring, popin 60%"
    assert quiet["run"], "hyprctl reload was not called"


def test_back_to_the_preset(cfg, quiet):
    a._set_active("dissolve")
    a.save_tuning(tuning({"open": "spring"}))
    a.set_variant("open", None)
    assert a.load_tuning()["overrides"] == {}


def test_menu_dissolve_is_refused_while_windows_do_not_dissolve(cfg, quiet):
    a._set_active("slide")
    a.set_variant("layers", "dissolve")
    assert a.load_tuning()["overrides"] == {}
    assert quiet["written"] == []
    assert quiet["notified"]


def test_set_speed_normal_clears_it(cfg, quiet):
    a._set_active("slide")
    a.set_speed("close", "slow")
    assert a.load_tuning()["speed"] == {"close": "slow"}
    a.set_speed("close", "normal")
    assert a.load_tuning()["speed"] == {}


def test_nothing_is_written_without_an_active_preset(cfg, quiet):
    a.set_variant("open", "pop")
    assert quiet["written"] == []
    assert a.load_tuning() == a.empty_tuning()


# ─────────────────────────── rows and navigation ───────────────────────────

def test_the_root_screen_lists_presets_and_the_four_categories(cfg):
    a._set_active("dissolve")
    rows = a.root_rows()
    assert [opts["info"] for _, opts in rows] == [
        "nav:presets", "nav:cat:open", "nav:cat:close", "nav:cat:workspaces", "nav:cat:layers",
    ]


def test_a_category_screen_marks_the_current_choices(cfg):
    a._set_active("dissolve")
    a.save_tuning(tuning({"close": "sand"}, {"close": "fast"}))
    rows = {opts["info"]: opts["display"] for _, opts in a.category_rows("close")}
    assert a.MARK_ACTIVE in rows["speed:close:fast"]
    assert a.MARK_ACTIVE not in rows["speed:close:normal"]
    assert a.MARK_ACTIVE in rows["var:close:sand"]
    assert a.MARK_ACTIVE not in rows["var:close:-"]


def test_the_menu_dissolve_row_explains_why_it_does_not_apply(cfg):
    a._set_active("slide")
    rows = {opts["info"]: opts["display"] for _, opts in a.category_rows("layers")}
    assert "var:layers:dissolve" in rows
    assert "(" in rows["var:layers:dissolve"]


def _run_mode(monkeypatch, capsys, retv, info="", argv=""):
    monkeypatch.setenv("ROFI_RETV", str(retv))
    monkeypatch.setenv("ROFI_INFO", info)
    monkeypatch.delenv("ROFI_ANIM_LEVEL", raising=False)
    monkeypatch.setattr(sys, "argv", ["anim_mode.py", argv])
    anim_mode.main()
    return capsys.readouterr().out


def test_navigation_opens_a_category(cfg, monkeypatch, capsys):
    a._set_active("dissolve")
    out = _run_mode(monkeypatch, capsys, 1, "nav:cat:workspaces")
    assert "var:workspaces:slide" in out


def test_back_returns_to_the_root(cfg, monkeypatch, capsys):
    a._set_active("dissolve")
    out = _run_mode(monkeypatch, capsys, 1, "up")
    assert "nav:cat:open" in out


def test_enter_on_a_variant_applies_it_and_stays_on_the_same_tile(cfg, quiet, monkeypatch, capsys):
    """Tuning is trying one thing after another, so the window stays open."""
    a._set_active("dissolve")
    out = _run_mode(monkeypatch, capsys, 1, "var:close:sand", "Песок")
    assert a.load_tuning()["overrides"] == {"close": "sand"}
    assert "var:close:dust" in out
    assert "\0new-selection\x1f" in out


def test_enter_on_a_preset_applies_it_and_closes(cfg, quiet, monkeypatch, capsys):
    out = _run_mode(monkeypatch, capsys, 1, "anim:slide", "slide")
    assert out == ""
    assert a.active_id() == "slide"


def test_preview_of_a_variant_starts_a_category_demo(cfg, monkeypatch, capsys):
    started = []
    monkeypatch.setattr(
        anim_mode, "start_preview", lambda *args, **kw: started.append((args, kw))
    )
    a._set_active("dissolve")
    _run_mode(monkeypatch, capsys, anim_mode.RETV_PREVIEW, "var:layers:pop", "Выскакивание")
    assert started == [(("cat", "layers", "var", "pop"),
                        {"level": "cat:layers", "select": "Выскакивание"})]


def test_preview_of_a_speed_starts_a_category_demo(cfg, monkeypatch, capsys):
    started = []
    monkeypatch.setattr(
        anim_mode, "start_preview", lambda *args, **kw: started.append((args, kw))
    )
    a._set_active("dissolve")
    _run_mode(monkeypatch, capsys, anim_mode.RETV_PREVIEW, "speed:open:slow")
    assert started[0][0] == ("cat", "open", "speed", "slow")


# ─────────────────────────── preview images ───────────────────────────

_spec = importlib.util.spec_from_file_location(
    "render_preview_cat", REPO / "tools" / "render_preview.py"
)
render_preview = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_preview)


@pytest.mark.parametrize("path", VARIANT_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_a_variant_preview_is_reproducible_and_not_blank(path):
    variant = load(path)
    first = render_preview.render(variant).tobytes()
    assert first == render_preview.render(variant).tobytes()
    grey = render_preview.render(variant).convert("L").tobytes()
    bright = sum(1 for value in grey if value > 200)
    assert bright > 500


@pytest.mark.parametrize("category", a.CATEGORIES)
def test_no_two_variants_of_a_category_look_the_same(category):
    """Within one category screen the tiles sit side by side and must differ.
    Same measure as the preset grid test."""
    thumbs = {}
    for variant in a.load_variants(category):
        image = render_preview.render(variant).convert("L").resize((40, 25))
        thumbs[variant["id"]] = list(image.tobytes())
    ids = sorted(thumbs)
    for i, first in enumerate(ids):
        for second in ids[i + 1:]:
            x, y = thumbs[first], thumbs[second]
            difference = sum(abs(p - q) for p, q in zip(x, y, strict=True)) / len(x)
            assert difference >= 1.5, f"{category}: {first} and {second} look the same"


# ─────────────────────────── preview fidelity (review 17.09) ───────────────────────────

def test_live_spec_resets_leaves_only_the_saved_config_sets():
    """keyword cannot unset a leaf: previewing "Speed: normal" while the saved
    config has an explicit slow windowsIn must push the inherited value."""
    preset = a.get("dissolve")
    saved = a.compose(preset, tuning(speed={"open": "slow"}))
    preview = a.compose(preset, tuning())
    live = a.live_spec(preview, saved)
    assert "windowsIn" not in preview["animations"]
    assert live["animations"]["windowsIn"] == a.HYPR_GLOBAL_DEFAULT
    assert live["animations"]["fadeOut"] == preview["animations"]["fadeOut"]


def test_live_spec_uses_the_presets_own_global():
    preset = a.get("instant")
    saved = a.compose(preset, tuning({"open": "spring"}))
    live = a.live_spec(a.compose(preset, tuning()), saved)
    assert live["animations"]["windowsIn"] == "0"


@pytest.mark.parametrize(("category", "expected"), [
    ("close", 2.0 * 1.6 + 0.4),     # fog close, slow: 34 ds * 1.6 → 5.4 s + 0.4
    ("workspaces", 0.8 + 0.4),      # fog preset workspaces: 8 ds
])
def test_wait_seconds_follows_the_animation(category, expected):
    composed = a.compose(a.get("fog"), tuning(speed={"close": "slow"}))
    if category == "close":
        assert a.wait_seconds(composed, "close") == round(34 * 1.6 / 10 + 0.4, 1)
    else:
        assert a.wait_seconds(composed, category) == round(expected, 1)


def test_wait_seconds_falls_back_to_global_for_unset_leaves():
    composed = a.compose(a.get("dissolve"), tuning())
    assert a.wait_seconds(composed, "open") == round(8 / 10 + 0.4, 1)


def test_preview_key_on_the_back_tile_stays_on_the_screen(cfg, monkeypatch, capsys):
    a._set_active("dissolve")
    out = _run_mode(monkeypatch, capsys, anim_mode.RETV_PREVIEW, "up:cat:close")
    assert "var:close:sand" in out


def test_close_change_says_when_menus_stop_dissolving(cfg, quiet):
    a._set_active("dissolve")
    a.save_tuning(tuning({"layers": "dissolve"}))
    a.set_variant("close", "shrink")
    assert quiet["notified"][-1].endswith(a.t("anim_menus_fell_back"))
