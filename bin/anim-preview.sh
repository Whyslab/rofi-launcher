#!/usr/bin/env bash
# anim-preview.sh — показать анимацию вживую и вернуть всё как было.
#
#   anim-preview.sh <preset-id>                       весь набор
#   anim-preview.sh cat <категория> var <вариант|->   одна категория с этим вариантом
#   anim-preview.sh cat <категория> speed <скорость>  одна категория с этой скоростью
#
# Категория показывается поверх текущих настроек: берётся активный набор и
# сохранённая донастройка, и меняется только выбранная строка — то есть видно
# ровно то, что получится после Enter.
#
# Порядок шагов здесь важен и выстрадан:
#
#  1. Окно анимаций закрывается ДО показа. rofi — поверхность layer-shell, и
#     обычное окно открывается под ней: тестовое окно было бы просто не видно.
#     Закрывает его сам anim_mode.py, отдав пустой вывод; сюда мы попадаем уже
#     без него.
#  2. Настройки применяются через `hyprctl keyword`, а НЕ записью в конфиг.
#     Проверено на этой машине: keyword ставит overridden=1, а `hyprctl reload`
#     возвращает overridden=0. То есть превью физически не может испортить
#     настройки — оно ничего не пишет.
#  3. Показ: для набора — окно открывается, съездить на соседний стол и
#     обратно, закрыть. Для категории — только её действие: открыть окно,
#     закрыть окно, переключить стол или открыть и закрыть меню.
#  4. `hyprctl reload` откатывает пункт 2.
#  5. Окно анимаций открывается заново на том же экране и той же строке
#     (ROFI_ANIM_LEVEL и ROFI_HUB_SELECT передаёт anim_mode.py).
#
# Если что-то падает посередине, откат всё равно случится: он в trap.

set -uo pipefail

[ -z "${1:-}" ] && exit 0

APP="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
CLASS="anim-preview"
TERMINAL="${ROFI_LAUNCHER_TERMINAL:-kitty}"
MENU_PID=""

# Откат — при любом выходе, включая ошибку и прерывание.
cleanup() {
    [ -n "$MENU_PID" ] && kill "$MENU_PID" >/dev/null 2>&1
    hyprctl dispatch closewindow "class:^(${CLASS})$" >/dev/null 2>&1
    hyprctl reload >/dev/null 2>&1
}
trap cleanup EXIT

# 1. Применить временно. Python печатает две строки: что показывать и сколько
#    секунд ждать, пока доиграет закрытие (из длительности самой анимации).
#    Путь к пакету передаём аргументом: внутри heredoc нет __file__.
PLAN="$(python3 - "$APP" "$@" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from rofi_hub.sections import animations as a

args = sys.argv[2:]
if args[0] == "cat":
    _, category, kind, value = args[:4]
    preset = a.current_preset()
    if preset is None or category not in a.CATEGORY_LEAVES:
        raise SystemExit(1)
    if kind == "var":
        tuning = a.preview_tuning(category, variant_id=value)
    else:
        tuning = a.preview_tuning(category, speed=value)
    composed = a.compose(preset, tuning)
    show = category
else:
    preset = a.get(args[0])
    if preset is None:
        raise SystemExit(1)
    composed = a.compose(preset, a.empty_tuning())
    show = "preset"

a.apply_live(composed)

def seconds(*leaves):
    spans = [a._duration(composed["animations"].get(leaf)) or 0 for leaf in leaves]
    return max(spans + [8]) / 10 + 0.4   # Hyprland's speed is in tenths of a second

print(show)
print(round(seconds("fadeOut", "windowsOut", "fadeLayersOut", "layersOut"), 1))
PY
)" || exit 0

SHOW="$(printf '%s\n' "$PLAN" | sed -n 1p)"
SETTLE="$(printf '%s\n' "$PLAN" | sed -n 2p)"

open_window() {
    # Правило windowrule по классу делает окно плавающим и по центру — см. установку.
    "$TERMINAL" --class "$CLASS" -e sh -c 'sleep 30' >/dev/null 2>&1 &
    # Ждём появления окна, а не гадаем таймаутом: на холодном старте терминал
    # может подниматься заметно дольше, чем на горячем.
    for _ in $(seq 1 40); do
        hyprctl clients -j 2>/dev/null | grep -q "\"${CLASS}\"" && break
        sleep 0.1
    done
}

close_window() {
    hyprctl dispatch closewindow "class:^(${CLASS})$" >/dev/null 2>&1
    sleep "$SETTLE"
}

switch_workspace() {
    local current next
    current="$(hyprctl activeworkspace -j 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",1))' 2>/dev/null || echo 1)"
    next=$(( current % 10 + 1 ))
    hyprctl dispatch workspace "$next" >/dev/null 2>&1
    sleep 1.1
    hyprctl dispatch workspace "$current" >/dev/null 2>&1
    sleep 1.1
}

show_menu() {
    printf 'Меню\nи уведомления\n' | rofi -dmenu -p "$(printf '')" >/dev/null 2>&1 &
    MENU_PID=$!
    sleep 1.4
    kill "$MENU_PID" >/dev/null 2>&1
    MENU_PID=""
    sleep "$SETTLE"
}

# 3. Показ.
case "$SHOW" in
    preset)     open_window; sleep 0.6; switch_workspace; close_window ;;
    open)       open_window; sleep 1.2; close_window ;;
    close)      open_window; sleep 0.9; close_window ;;
    workspaces) switch_workspace ;;
    layers)     show_menu ;;
esac

# 5. Откат делает trap. Открыть окно анимаций заново там же.
setsid "$APP/bin/hub-animations.sh" >/dev/null 2>&1 &
