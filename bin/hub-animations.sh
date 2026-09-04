#!/bin/sh
# Сетка анимаций. Своё окно и своя тема: превью крупные, а rofi не умеет
# менять раскладку по ходу сессии.
#
# Ctrl+Alt+Пробел (kb-custom-1) — показать пресет вживую.
#
# Не Ctrl+Пробел: он уже занят самим rofi под kb-row-select, и при попытке
# переопределить его rofi отказывается открывать окно и показывает диалог
# ошибки вместо сетки. Пробел от раскладки не зависит, дубль по keysym не нужен.

APP="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"

exec rofi -show anim -modes "anim:$APP/rofi_hub/anim_mode.py" \
  -theme "$APP/themes/grid.rasi" \
  -kb-custom-1 "Control+Alt+space"
