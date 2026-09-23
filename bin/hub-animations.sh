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

# Сетке нужна своя тема с крупными превью. Переопределяется отдельно от
# темы списка: они решают разные задачи и одной строкой не заменяются.
THEME="${ROFI_LAUNCHER_GRID_THEME-$APP/themes/grid.rasi}"

# Хаб запускает этот скрипт и сразу закрывается сам, но его rofi ещё держит
# замок на pid-файле. Второй rofi, который стартует раньше, чем первый его
# отпустил, пишет «Rofi already running?» и молча выходит — окно анимаций
# «иногда не открывается». Ждём, пока замок освободится (не дольше 3 с).
PIDFILE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/rofi.pid"
if [ -e "$PIDFILE" ] && command -v flock >/dev/null 2>&1; then
  flock -w 3 "$PIDFILE" true 2>/dev/null
fi

exec rofi -show anim -modes "anim:$APP/rofi_hub/anim_mode.py" \
  ${THEME:+-theme "$THEME"} \
  -kb-custom-1 "Control+Alt+space"
