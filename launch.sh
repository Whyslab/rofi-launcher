#!/bin/sh
# The launcher's entry point. Every rofi flag lives here rather than in
# ~/.config/rofi/config.rasi, so that these key overrides do not leak into the
# other rofi invocations on the machine (a clipboard manager, a command palette,
# anything else bound to rofi).
#
# IMPORTANT, about letter keys. A binding resolves by SYMBOL, not by physical
# key, so the same Ctrl+P is a different binding in a different keyboard layout:
#   Latin,    without Shift : p              Latin,    with Shift : P
#   Cyrillic, without Shift : Cyrillic_ze    Cyrillic, with Shift : Cyrillic_ZE
# List every variant, comma-separated, or the key silently does nothing half the
# time. Arrow keys do not depend on the layout and need no duplicates.
#
# kb-custom-2 (unpin via Ctrl+Shift+P) is deliberately left unbound: with a
# non-Latin layout it failed to fire even with all four keysym spellings, and
# Ctrl+P already works as a toggle. The handler in launcher.py is still there,
# so any key without Shift can be bound to it here.

SELF_DIR=$(dirname "$(readlink -f "$0")")
SCRIPT="${ROFI_LAUNCHER_SCRIPT:-$SELF_DIR/launcher.py}"

# The bundled theme, unless one is named. Set ROFI_LAUNCHER_THEME to your own
# .rasi file, or to an empty string to use whatever your rofi config already does.
if [ -z "${ROFI_LAUNCHER_THEME+set}" ]; then
    THEME="$SELF_DIR/monochrome.rasi"
else
    THEME="$ROFI_LAUNCHER_THEME"
fi

set -- -show apps -modes "apps:$SCRIPT"
[ -n "$THEME" ] && [ -r "$THEME" ] && set -- "$@" -theme "$THEME"

exec rofi "$@" \
  -kb-row-up   "Up" \
  -kb-custom-1 "Control+p,Control+Cyrillic_ze" \
  -kb-custom-3 "Control+Alt+Up" \
  -kb-custom-4 "Control+Alt+Down" \
  -kb-custom-5 "Alt+Left,Alt+BackSpace"
