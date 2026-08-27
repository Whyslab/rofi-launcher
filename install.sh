#!/usr/bin/env bash
# install.sh — install the rofi launcher.
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
APP_DIR="${DATA_HOME}/rofi-launcher"
CFG_DIR="${CONFIG_HOME}/rofi-launcher"

run() { if (( DRY )); then printf '   would run: %s\n' "$*"; else "$@"; fi; }

say "Install root: ${PREFIX:-$HOME}"
(( DRY )) && warn "dry run — nothing will be written"

if [[ -z "$PREFIX" ]]; then
    command -v rofi >/dev/null || die "rofi is not installed"
    command -v python3 >/dev/null || die "python3 is not installed"
    ok "rofi $(rofi -version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1) and python3 present"
    command -v gio >/dev/null || warn "gio not found (glib2) — launching falls back to parsing Exec by hand"
fi

say "Installing the launcher"
run install -d -m 755 "$APP_DIR"
run install -m 755 "${SRC_DIR}/rofi_launcher/launcher.py" "${APP_DIR}/launcher.py"
run install -m 755 "${SRC_DIR}/launch.sh" "${APP_DIR}/launch.sh"
run install -m 644 "${SRC_DIR}/themes/monochrome.rasi" "${APP_DIR}/monochrome.rasi"
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

if [[ -n "$PREFIX" ]]; then
    echo; ok "Sandbox install finished: ${PREFIX}"
    exit 0
fi

echo
ok "Installation finished."
echo
echo "  Try it now:   ${APP_DIR}/launch.sh"
echo
echo "  Bind it (Hyprland — replace your existing SUPER, R binding):"
echo "    \$menu = ${APP_DIR}/launch.sh"
echo "    bind = SUPER, R, exec, \$menu"
echo
echo "  Sway / i3:"
echo "    bindsym \$mod+r exec ${APP_DIR}/launch.sh"
