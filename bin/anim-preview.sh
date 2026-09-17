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

# 1. Применить временно. Python печатает план: что показывать и сколько ждать
#    каждое действие — длительности берутся из самой анимации, иначе медленные
#    варианты обрывались на середине. Путь к пакету передаём аргументом: внутри
#    heredoc нет __file__.
reopen() {
    # Вернуть настройки ДО того, как окно анимаций откроется снова: иначе оно
    # проиграет своё появление ещё с показанными, а не с сохранёнными.
    hyprctl reload >/dev/null 2>&1
    setsid "$APP/bin/hub-animations.sh" >/dev/null 2>&1 &
}

PLAN="$(python3 - "$APP" "$@" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from rofi_hub.sections import animations as a
from rofi_hub.strings import t

args = sys.argv[2:]
saved_preset = a.current_preset()
if args[0] == "cat":
    _, category, kind, value = args[:4]
    if saved_preset is None or category not in a.CATEGORY_LEAVES:
        a.notify(t("anim_no_preset"))
        raise SystemExit(1)
    if kind == "var":
        tuning = a.preview_tuning(category, variant_id=value)
    else:
        tuning = a.preview_tuning(category, speed=value)
    composed = a.compose(saved_preset, tuning)
    show = category
else:
    preset = a.get(args[0])
    if preset is None:
        raise SystemExit(1)
    composed = a.compose(preset, a.empty_tuning())
    show = "preset"

# The running config is the saved one; leaves it sets that the preview does not
# must be reset, or the demo shows the old value (see live_spec).
saved = a.compose(saved_preset, a.load_tuning()) if saved_preset else {"animations": {}}
a.apply_live(a.live_spec(composed, saved))

print(show)
for category in ("open", "close", "workspaces", "layers"):
    print(a.wait_seconds(composed, category))
PY
)" || { reopen; exit 0; }

line() { printf '%s\n' "$PLAN" | sed -n "${1}p"; }
SHOW="$(line 1)"
WAIT_OPEN="$(line 2)"
WAIT_CLOSE="$(line 3)"
WAIT_WORKSPACE="$(line 4)"
WAIT_MENU="$(line 5)"

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
    sleep "$WAIT_CLOSE"
}

switch_workspace() {
    local current next
    current="$(hyprctl activeworkspace -j 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",1))' 2>/dev/null || echo 1)"
    next=$(( current % 10 + 1 ))
    hyprctl dispatch workspace "$next" >/dev/null 2>&1
    sleep "$WAIT_WORKSPACE"
    hyprctl dispatch workspace "$current" >/dev/null 2>&1
    sleep "$WAIT_WORKSPACE"
}

show_menu() {
    printf 'Меню\nи уведомления\n' | rofi -dmenu -p "$(printf '')" >/dev/null 2>&1 &
    MENU_PID=$!
    sleep "$WAIT_MENU"
    sleep 0.6
    kill "$MENU_PID" >/dev/null 2>&1
    MENU_PID=""
    sleep "$WAIT_MENU"
}

# 3. Показ.
case "$SHOW" in
    preset)     open_window; sleep "$WAIT_OPEN"; switch_workspace; close_window ;;
    open)       open_window; sleep "$WAIT_OPEN"; sleep 0.6; close_window ;;
    close)      open_window; sleep "$WAIT_OPEN"; close_window ;;
    workspaces) switch_workspace ;;
    layers)     show_menu ;;
esac

# 4–5. Вернуть настройки и открыть окно анимаций заново там же. trap тоже
#      сделает reload — на случай, если до этой строки не дошли.
reopen
