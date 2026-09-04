#!/usr/bin/env bash
# install.sh — install the rofi hub.
#
# Everything goes under your home directory; nothing needs root.
#
#   ./install.sh                    install for the current user
#   ./install.sh --dry-run          print every step, change nothing
#   ./install.sh --prefix /tmp/test install into a sandbox

set -Eeuo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
say()  { printf '%b\n' "${BLUE}==>${NC} $*"; }
ok()   { printf '%b\n' "${GREEN}  ok${NC} $*"; }
warn() { printf '%b\n' "${YELLOW}  !!${NC} $*"; }
die()  { printf '%b\n' "${RED}error:${NC} $*" >&2; exit 1; }

DRY=0; PREFIX=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY=1; shift ;;
        --prefix)  PREFIX="${2%/}"; shift 2 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
done

[[ $EUID -ne 0 ]] || die "do not run this as root — it installs into your home directory"

SRC_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DATA_HOME="${PREFIX}${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${PREFIX}${XDG_CONFIG_HOME:-$HOME/.config}"
CACHE_HOME="${PREFIX}${XDG_CACHE_HOME:-$HOME/.cache}"
APP_DIR="${DATA_HOME}/rofi-launcher"
CFG_DIR="${CONFIG_HOME}/rofi-launcher"
PREVIEW_DIR="${CACHE_HOME}/rofi-launcher/anim-previews"

run() { if (( DRY )); then printf '   would run: %s\n' "$*"; else "$@"; fi; }

say "Install root: ${PREFIX:-$HOME}"
(( DRY )) && warn "dry run — nothing will be written"

if [[ -z "$PREFIX" ]]; then
    command -v rofi >/dev/null || die "rofi is not installed"
    command -v python3 >/dev/null || die "python3 is not installed"
    ok "rofi $(rofi -version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1) and python3 present"
    command -v gio >/dev/null || warn "gio not found (glib2) — launching falls back to parsing Exec by hand"
    command -v cliphist >/dev/null || warn "cliphist not found — the clipboard section will say so"
    command -v hyprctl >/dev/null || warn "hyprctl not found — the windows and animations sections need it"
    python3 -c 'import PIL' 2>/dev/null || warn "python-pillow not found — animation previews cannot be drawn"
fi

say "Installing the hub"
run install -d -m 755 "$APP_DIR" "$APP_DIR/rofi_hub" "$APP_DIR/rofi_hub/sections" \
    "$APP_DIR/bin" "$APP_DIR/themes" "$APP_DIR/data" "$APP_DIR/data/presets" \
    "$APP_DIR/tools"

for f in "${SRC_DIR}"/rofi_hub/*.py; do
    run install -m 644 "$f" "$APP_DIR/rofi_hub/$(basename "$f")"
done
run chmod 755 "$APP_DIR/rofi_hub/hub.py" "$APP_DIR/rofi_hub/anim_mode.py"
for f in "${SRC_DIR}"/rofi_hub/sections/*.py; do
    run install -m 644 "$f" "$APP_DIR/rofi_hub/sections/$(basename "$f")"
done
for f in "${SRC_DIR}"/bin/*.sh; do
    run install -m 755 "$f" "$APP_DIR/bin/$(basename "$f")"
done
for f in "${SRC_DIR}"/themes/*.rasi; do
    run install -m 644 "$f" "$APP_DIR/themes/$(basename "$f")"
done
run install -m 644 "${SRC_DIR}/data/emoji.ru.json" "$APP_DIR/data/emoji.ru.json"
for f in "${SRC_DIR}"/data/presets/*.json; do
    run install -m 644 "$f" "$APP_DIR/data/presets/$(basename "$f")"
done
run install -m 755 "${SRC_DIR}/tools/render_preview.py" "$APP_DIR/tools/render_preview.py"
ok "installed to ${APP_DIR}"

say "Setting up configuration"
run install -d -m 755 "$CFG_DIR"
if [[ -f "${CFG_DIR}/folders.conf" ]]; then
    warn "folders.conf already exists — keeping it as is"
else
    run install -m 644 "${SRC_DIR}/config/folders.example.conf" "${CFG_DIR}/folders.conf"
    ok "folders.conf written (edit it to change the folders)"
fi
if [[ -f "${CFG_DIR}/favorites.list" ]]; then
    warn "favorites.list already exists — keeping it as is"
else
    # Deliberately left empty rather than seeded with guesses: an unpinned root
    # shows the folders, and Ctrl+P is how pinning is meant to be discovered.
    if (( DRY )); then
        printf '   would create an empty favorites.list\n'
    else
        printf '# Pinned applications. Pin them with Ctrl+P inside a folder.\n' > "${CFG_DIR}/favorites.list"
        chmod 644 "${CFG_DIR}/favorites.list"
    fi
    ok "favorites.list created empty"
fi

say "Drawing the animation previews"
if (( DRY )); then
    printf '   would render previews into %s\n' "$PREVIEW_DIR"
elif python3 -c 'import PIL' 2>/dev/null; then
    run install -d -m 755 "$PREVIEW_DIR"
    python3 "${SRC_DIR}/tools/render_preview.py" --out "$PREVIEW_DIR" >/dev/null
    ok "previews in ${PREVIEW_DIR}"
else
    warn "skipped — python-pillow is not installed (the grid falls back to plain rows)"
fi

if [[ -n "$PREFIX" ]]; then
    echo; ok "Sandbox install finished: ${PREFIX}"
    exit 0
fi

# The emoji section renders through rofi's own font. The fontconfig rules that
# ship on most systems only attach Noto Color Emoji to the generic families, so
# an explicit family — which is what a launcher theme normally sets — gets Font
# Awesome's monochrome glyphs or tofu instead of emoji.
say "Checking that emoji can render"
if fc-match "JetBrainsMono Nerd Font:charset=1F525" 2>/dev/null | grep -qi "emoji"; then
    ok "emoji fall back to a colour emoji font"
else
    warn "emoji may render as monochrome icons or blank boxes"
    warn "add a rule for your rofi font to ~/.config/fontconfig/fonts.conf:"
    cat <<'XML'
      <match target="pattern">
        <test name="family"><string>JetBrainsMono Nerd Font</string></test>
        <edit name="family" mode="append" binding="weak"><string>Noto Color Emoji</string></edit>
      </match>
XML
fi

echo
ok "Installation finished."
echo
echo "  Try it now:   ${APP_DIR}/bin/hub.sh"
echo
echo "  Bind it (Hyprland):"
echo "    \$menu = ${APP_DIR}/bin/hub.sh"
echo "    bind = SUPER, R, exec, \$menu"
echo "    bind = CTRL, J, exec, ${APP_DIR}/bin/hub-clipboard.sh"
echo "    bind = SUPER SHIFT, W, exec, ${APP_DIR}/bin/hub-wallpaper.sh"
echo
echo "  The live animation preview needs a floating test window:"
echo "    windowrule = match:class ^(anim-preview)\$, float true, size 600 400, center true"
