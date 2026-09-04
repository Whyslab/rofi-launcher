#!/usr/bin/env bash
# anim-preview.sh <preset-id> — показать пресет вживую и вернуть всё как было.
#
# Порядок шагов здесь важен и выстрадан:
#
#  1. Сетка анимаций закрывается ДО показа. rofi — поверхность layer-shell, и
#     обычное окно открывается под ней: тестовое окно было бы просто не видно.
#     Закрывает её сам anim_mode.py, отдав пустой вывод; сюда мы попадаем уже
#     без неё.
#  2. Пресет применяется через `hyprctl keyword`, а НЕ записью в конфиг.
#     Проверено на этой машине: keyword ставит overridden=1, а `hyprctl reload`
#     возвращает overridden=0. То есть превью физически не может испортить
#     настройки — оно ничего не пишет.
#  3. Тестовое окно открывается, переезжает на соседний стол и обратно,
#     затем закрывается. За один проход видно windowsIn, workspaces,
#     windowsOut и распад.
#  4. `hyprctl reload` откатывает пункт 2.
#  5. Сетка открывается заново на том же пресете.
#
# Если что-то падает посередине, откат всё равно случится: он в trap.

set -uo pipefail

PRESET="${1:-}"
[ -z "$PRESET" ] && exit 0

APP="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
CLASS="anim-preview"
TERMINAL="${ROFI_LAUNCHER_TERMINAL:-kitty}"

# Откат — при любом выходе, включая ошибку и прерывание.
cleanup() {
    hyprctl dispatch closewindow "class:^(${CLASS})$" >/dev/null 2>&1
    hyprctl reload >/dev/null 2>&1
}
trap cleanup EXIT

# 1. Применить пресет временно. Путь к пакету передаём аргументом: внутри
#    heredoc нет __file__, по которому его можно было бы вычислить.
if ! python3 - "$APP" "$PRESET" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from rofi_hub.sections import animations
preset = animations.get(sys.argv[2])
if preset is None:
    raise SystemExit(1)
animations.apply_live(preset)
PY
then
    exit 0
fi

# 2. Тестовое окно. Правило windowrule по классу делает его плавающим и по
#    центру — см. установку.
"$TERMINAL" --class "$CLASS" -e sh -c 'sleep 4' >/dev/null 2>&1 &

# Ждём появления окна, а не гадаем таймаутом: на холодном старте терминал
# может подниматься заметно дольше, чем на горячем.
for _ in $(seq 1 40); do
    hyprctl clients -j 2>/dev/null | grep -q "\"${CLASS}\"" && break
    sleep 0.1
done

sleep 0.6

# 3. Съездить на соседний стол и обратно — это и есть анимация переключения.
CURRENT="$(hyprctl activeworkspace -j 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",1))' 2>/dev/null || echo 1)"
NEXT=$(( CURRENT % 10 + 1 ))

hyprctl dispatch workspace "$NEXT" >/dev/null 2>&1
sleep 0.9
hyprctl dispatch workspace "$CURRENT" >/dev/null 2>&1
sleep 0.9

# 4. Закрыть окно — распад виден здесь.
hyprctl dispatch closewindow "class:^(${CLASS})$" >/dev/null 2>&1

# Дать распаду доиграть: длительность берётся из fadeOut пресета, самый
# длинный из штатных — 2.5 с.
sleep 2.8

# 5. Откат делает trap. Открыть сетку заново на том же пресете.
ROFI_HUB_SELECT="$PRESET" setsid "$APP/bin/hub-animations.sh" >/dev/null 2>&1 &
