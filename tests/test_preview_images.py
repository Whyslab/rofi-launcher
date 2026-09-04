"""
Preview images.

Rofi cannot animate: its binary links only gdk_pixbuf_new_from_file_at_scale,
the single-frame loader, with no gdk_pixbuf_animation_new_from_file anywhere in
it. A GIF would render as its first frame — for a fade-out, an empty rectangle.
So the preview is a still picture computed from the preset's own numbers, and
the thing worth testing about it is that it is reproducible: install.sh
regenerates these, and a picture that changed on every run would churn caches
and make any visual comparison meaningless.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# tools/ is a directory of scripts, not an importable package.
_spec = importlib.util.spec_from_file_location(
    "render_preview", REPO / "tools" / "render_preview.py"
)
render_preview = importlib.util.module_from_spec(_spec)
sys.modules["render_preview"] = render_preview
_spec.loader.exec_module(render_preview)

PRESETS = sorted((REPO / "data" / "presets").glob("*.json"))


def _png_bytes(preset, tmp_path, name):
    target = tmp_path / name
    render_preview.render(preset).save(target, "PNG", optimize=False)
    return target.read_bytes()


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_a_preview_is_byte_for_byte_reproducible(path, tmp_path):
    preset = json.loads(path.read_text(encoding="utf-8"))
    first = _png_bytes(preset, tmp_path, "a.png")
    second = _png_bytes(preset, tmp_path, "b.png")
    assert first == second


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_a_preview_is_not_blank(path):
    """A tile that is all background says nothing and would look like a bug."""
    preset = json.loads(path.read_text(encoding="utf-8"))
    image = render_preview.render(preset)
    bright = sum(1 for value in image.convert("L").tobytes() if value > 200)
    assert bright > 500, "the window is not visible in the tile"


def test_presets_do_not_all_look_the_same():
    """Three of the presets differ only in the dissolve plugin's numbers. If the
    renderer ignored those, the grid would show three identical tiles and be
    useless for choosing between them."""
    images = {}
    for path in PRESETS:
        preset = json.loads(path.read_text(encoding="utf-8"))
        images[preset["id"]] = render_preview.render(preset).tobytes()
    assert len(set(images.values())) == len(images), "two presets render identically"


def test_the_dissolve_numbers_actually_change_the_picture():
    base = json.loads((REPO / "data" / "presets" / "dissolve.json").read_text(encoding="utf-8"))
    chunky = json.loads(json.dumps(base))
    chunky["dissolve"]["block_size"] = 12
    chunky["dissolve"]["spread"] = 2.0
    assert render_preview.render(base).tobytes() != render_preview.render(chunky).tobytes()
