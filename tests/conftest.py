import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# The application logic moved from rofi_launcher/launcher.py into
# rofi_hub/sections/apps.py when the launcher became the hub. The existing
# tests import it as `launcher`, and keeping that name working means they keep
# testing the same behaviour instead of being rewritten alongside the code they
# are supposed to be guarding.
from rofi_hub.sections import apps as launcher  # noqa: E402

sys.modules.setdefault("launcher", launcher)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_hub_config(tmp_path, monkeypatch):
    """The hub screen reads two hand-edited lists from ~/.config; a test must
    never see the developer's own ones."""
    monkeypatch.setattr(launcher, "SHORTCUTS_FILE", tmp_path / "hub-shortcuts.list")
    monkeypatch.setattr(launcher, "HIDDEN_FILE", tmp_path / "hub-hidden.list")
