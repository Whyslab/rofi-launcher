"""
Wrong-layout search: typing an app's name without switching keyboard layout
should still find it.
"""
import importlib

import launcher


def test_the_default_pair_translates_both_ways():
    variants = launcher.layout_variants("ghjdjlybr")
    assert variants, "a Latin string should produce a variant in the other layout"


def test_text_that_does_not_change_produces_no_variant():
    assert launcher.layout_variants("12345") == []


def test_the_layout_can_be_replaced(monkeypatch):
    monkeypatch.setenv("ROFI_LAUNCHER_LAYOUT_PRIMARY", "abc")
    monkeypatch.setenv("ROFI_LAUNCHER_LAYOUT_SECONDARY", "xyz")
    reloaded = importlib.reload(launcher)
    try:
        assert "xyz" in reloaded.layout_variants("abc")
        assert "abc" in reloaded.layout_variants("xyz")
    finally:
        monkeypatch.delenv("ROFI_LAUNCHER_LAYOUT_PRIMARY", raising=False)
        monkeypatch.delenv("ROFI_LAUNCHER_LAYOUT_SECONDARY", raising=False)
        importlib.reload(launcher)


def test_an_empty_layout_switches_the_feature_off(monkeypatch):
    monkeypatch.setenv("ROFI_LAUNCHER_LAYOUT_PRIMARY", "")
    reloaded = importlib.reload(launcher)
    try:
        assert reloaded.layout_variants("ghjdjlybr") == []
    finally:
        monkeypatch.delenv("ROFI_LAUNCHER_LAYOUT_PRIMARY", raising=False)
        importlib.reload(launcher)


def test_a_mismatched_layout_pair_is_refused_rather_than_mistranslating(monkeypatch):
    """Unequal halves would map characters to the wrong keys — do nothing instead."""
    monkeypatch.setenv("ROFI_LAUNCHER_LAYOUT_PRIMARY", "abcdef")
    monkeypatch.setenv("ROFI_LAUNCHER_LAYOUT_SECONDARY", "xy")
    reloaded = importlib.reload(launcher)
    try:
        assert reloaded.layout_variants("abc") == []
    finally:
        monkeypatch.delenv("ROFI_LAUNCHER_LAYOUT_PRIMARY", raising=False)
        monkeypatch.delenv("ROFI_LAUNCHER_LAYOUT_SECONDARY", raising=False)
        importlib.reload(launcher)


def test_a_default_layout_string_containing_a_colon_still_works():
    """
    The default primary layout contains ":" as an actual key. An earlier version
    packed both halves into one colon-separated variable, which silently split
    the layout in the middle and switched wrong-layout search off entirely.
    """
    assert ":" in launcher._DEFAULT_PRIMARY
    assert len(launcher._DEFAULT_PRIMARY) == len(launcher._DEFAULT_SECONDARY)
    assert launcher._LAYOUT_TABLES, "the default layout pair must produce tables"
