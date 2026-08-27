#!/usr/bin/env bash
# uninstall.sh — remove the rofi launcher.
#
#   ./uninstall.sh                    remove the program, keep your pins
#   ./uninstall.sh --purge            also remove folders.conf, pins and cache
#   ./uninstall.sh --dry-run          print what would happen
#   ./uninstall.sh --prefix /tmp/test undo a sandbox install

set -Eeuo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
say()  { printf '%b\n' "${BLUE}==>${NC} $*"; }
ok()   { printf '%b\n' "${GREEN}  ok${NC} $*"; }
warn() { printf '%b\n' "${YELLOW}  !!${NC} $*"; }
die()  { printf '%b\n' "${RED}error:${NC} $*" >&2; exit 1; }

DRY=0; PURGE=0; PREFIX=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY=1; shift ;;
        --purge)   PURGE=1; shift ;;
        --prefix)  PREFIX="${2%/}"; shift 2 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
done

DATA_HOME="${PREFIX}${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${PREFIX}${XDG_CONFIG_HOME:-$HOME/.config}"
CACHE_HOME="${PREFIX}${XDG_CACHE_HOME:-$HOME/.cache}"

run() { if (( DRY )); then printf '   would run: %s\n' "$*"; else "$@"; fi; }
(( DRY )) && warn "dry run — nothing will be removed"

say "Removing the launcher"
run rm -rf "${DATA_HOME}/rofi-launcher"
ok "program removed"

if (( PURGE )); then
    say "--purge: removing configuration and cache"
    run rm -rf "${CONFIG_HOME}/rofi-launcher" "${CACHE_HOME}/rofi-launcher"
    ok "folders, pins and the usage cache removed"
else
    say "Keeping your configuration"
    echo "   ${CONFIG_HOME}/rofi-launcher/folders.conf"
    echo "   ${CONFIG_HOME}/rofi-launcher/favorites.list"
fi

echo
warn "Your key binding still points here — remove or re-point it:"
echo "   the SUPER+R line in hyprland.conf (or your compositor's config)"
echo
ok "Uninstall finished."
