#!/bin/sh
# Единая точка входа хаба (SUPER+R).
#
# Все флаги rofi живут здесь, а не в ~/.config/rofi/config.rasi, чтобы
# переопределения клавиш не протекли в остальные вызовы rofi на этой машине
# (backup-manager на Super+Shift+B, пикер обоев).
#
# ВАЖНО про буквенные клавиши. Привязка резолвится по СИМВОЛУ, а не по
# физической клавише, поэтому один и тот же Ctrl+P в разных раскладках — это
# разные привязки:
#   английская, без Shift : p              английская, с Shift : P
#   русская,    без Shift : Cyrillic_ze    русская,    с Shift : Cyrillic_ZE
# Перечисляем оба варианта через запятую, иначе клавиша молча не работает в
# половине случаев. Стрелки от раскладки не зависят, им дубли не нужны.
#
# Первый аргумент — раздел, на котором открыться (clip, win, emoji, shot,
# power). Пусто — корень.

APP="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
HUB="$APP/rofi_hub/hub.py"

ROFI_DATA="${1:-}"
export ROFI_DATA

exec rofi -show hub -modes "hub:$HUB" \
  -theme "$APP/themes/hub.rasi" \
  -kb-row-up   "Up" \
  -kb-custom-1 "Control+p,Control+Cyrillic_ze" \
  -kb-custom-3 "Control+Alt+Up" \
  -kb-custom-4 "Control+Alt+Down" \
  -kb-custom-5 "Alt+Left,Alt+BackSpace" \
  -kb-custom-6 "Control+x,Control+Cyrillic_che"
