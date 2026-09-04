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
# Цифры 1..5 открывают раздел откуда угодно, а не только из корня. Цена
# честная: rofi вешает привязку на всю сессию, поэтому цифру больше нельзя
# набрать в строке фильтра. Взамен переход между разделами — одно нажатие.
#
# Tab отбирается у встроенного kb-element-next: в менеджере приложений он
# переключает «избранное ↔ все приложения», и это самая частая операция.
#
# Первый аргумент — раздел, на котором открыться (apps, clip, emoji).
# Пусто — корень.

APP="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
HUB="$APP/rofi_hub/hub.py"

# Своя тема, а не ~/.config/rofi/config.rasi: там список обрезан десятью
# строками, и разделы хаба уезжали за нижний край экрана. Пустое значение
# ROFI_LAUNCHER_THEME означает "взять мой собственный конфиг rofi".
THEME="${ROFI_LAUNCHER_THEME-$APP/themes/hub.rasi}"

ROFI_DATA="${1:-}"
export ROFI_DATA

exec rofi -show hub -modes "hub:$HUB" \
  ${THEME:+-theme "$THEME"} \
  -kb-row-up   "Up" \
  -kb-element-next "" \
  -kb-custom-1 "Control+p,Control+Cyrillic_ze" \
  -kb-custom-3 "Control+Alt+Up" \
  -kb-custom-4 "Control+Alt+Down" \
  -kb-custom-5 "Alt+Left,Alt+BackSpace" \
  -kb-custom-6 "Control+x,Control+Cyrillic_che" \
  -kb-custom-7 "Tab" \
  -kb-custom-8  "1" \
  -kb-custom-9  "2" \
  -kb-custom-10 "3" \
  -kb-custom-11 "4" \
  -kb-custom-12 "5"
