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
