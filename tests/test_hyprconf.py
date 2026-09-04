"""
Generating Hyprland configuration from a preset.

Hyprland is mid-migration from .conf to Lua, and on a machine where both files
exist the .lua wins and the .conf is ignored completely. Generating the wrong
one is not a cosmetic mistake: the preset would silently do nothing at all.
"""
import pytest

from rofi_hub import hyprconf

PRESET = {
    "id": "sample",
    "beziers": {"soft": [0.05, 0.9, 0.1, 1.0]},
    "animations": {
        "windowsIn": "1, 5, soft, popin 90%",
        "fadeOut": "1, 20, default",
    },
    "dissolve": {"enabled": 1, "block_size": 3, "key_leak_fix": 0},
}


def test_conf_output_has_the_classic_shape():
    text = hyprconf.render(PRESET, "conf")
    assert "bezier = soft, 0.05, 0.9, 0.1, 1" in text
    assert "animation = windowsIn, 1, 5, soft, popin 90%" in text
    assert "block_size = 3" in text


def test_lua_output_uses_the_lua_api():
    text = hyprconf.render(PRESET, "lua")
    assert 'hl.curve("soft", { type = "bezier", points = { { 0.05, 0.9 }, { 0.1, 1 } } })' in text
    assert 'leaf = "windowsIn"' in text
    assert 'style = "popin 90%"' in text
    assert "hl.config({ plugin = { dissolve = {" in text


@pytest.mark.parametrize("fmt", ["conf", "lua"])
def test_protected_keys_never_reach_the_generated_file(fmt):
    """key_leak_fix is in the sample preset on purpose: the generator has to
    drop it even when a preset asks for it."""
    assert "key_leak_fix" not in hyprconf.render(PRESET, fmt)


@pytest.mark.parametrize("fmt", ["conf", "lua"])
def test_a_disabled_animation_stays_disabled(fmt):
    off = {"id": "off", "animations": {"global": "0"}, "dissolve": {"enabled": 0}}
    text = hyprconf.render(off, fmt)
    if fmt == "lua":
        assert "enabled = false" in text
    else:
        assert "animation = global, 0" in text


def test_the_generated_file_says_not_to_edit_it():
    for fmt in ("conf", "lua"):
        assert "do not edit by hand" in hyprconf.render(PRESET, fmt)


def test_lua_wins_when_both_configs_exist(tmp_path, monkeypatch):
    lua, conf = tmp_path / "hyprland.lua", tmp_path / "hyprland.conf"
    lua.write_text("")
    conf.write_text("")
    monkeypatch.setattr(hyprconf, "LUA_CONFIG", lua)
    monkeypatch.setattr(hyprconf, "CONF_CONFIG", conf)
    monkeypatch.setattr(hyprconf, "GENERATED_LUA", tmp_path / "animations.lua")
    monkeypatch.setattr(hyprconf, "GENERATED_CONF", tmp_path / "animations.conf")

    fmt, path = hyprconf.target()
    assert fmt == "lua"
    assert path.name == "animations.lua"


def test_conf_is_used_when_there_is_no_lua(tmp_path, monkeypatch):
    conf = tmp_path / "hyprland.conf"
    conf.write_text("")
    monkeypatch.setattr(hyprconf, "LUA_CONFIG", tmp_path / "hyprland.lua")
    monkeypatch.setattr(hyprconf, "CONF_CONFIG", conf)
    monkeypatch.setattr(hyprconf, "GENERATED_LUA", tmp_path / "animations.lua")
    monkeypatch.setattr(hyprconf, "GENERATED_CONF", tmp_path / "animations.conf")

    fmt, path = hyprconf.target()
    assert fmt == "conf"
    assert path.name == "animations.conf"


def test_the_include_line_matches_the_format(tmp_path, monkeypatch):
    monkeypatch.setattr(hyprconf, "LUA_CONFIG", tmp_path / "hyprland.lua")
    monkeypatch.setattr(hyprconf, "CONF_CONFIG", tmp_path / "hyprland.conf")
    monkeypatch.setattr(hyprconf, "GENERATED_CONF", tmp_path / "animations.conf")
    assert hyprconf.include_line().startswith("source = ")

    (tmp_path / "hyprland.lua").write_text("")
    monkeypatch.setattr(hyprconf, "GENERATED_LUA", tmp_path / "animations.lua")
    assert hyprconf.include_line().startswith("dofile(")


def test_both_formats_are_written(tmp_path, monkeypatch):
    """The main config includes the generated file by name. If only the active
    format existed, switching Hyprland from .conf to .lua would leave that
    include pointing at nothing — and a Lua error drops the compositor to
    emergency keybinds."""
    monkeypatch.setattr(hyprconf, "LUA_CONFIG", tmp_path / "hyprland.lua")
    monkeypatch.setattr(hyprconf, "CONF_CONFIG", tmp_path / "hyprland.conf")
    monkeypatch.setattr(hyprconf, "GENERATED_CONF", tmp_path / "animations.conf")
    monkeypatch.setattr(hyprconf, "GENERATED_LUA", tmp_path / "animations.lua")

    active = hyprconf.write(PRESET)

    assert active.name == "animations.conf"
    assert (tmp_path / "animations.conf").is_file()
    assert (tmp_path / "animations.lua").is_file()
    assert "hl.curve" in (tmp_path / "animations.lua").read_text(encoding="utf-8")
