"""
User-facing text, picked by locale.

Why this file exists at all: the launcher used to be maintained as two forked
copies of the same script — an English one in the repository and a Russian one
installed under ~/.local/share. They drifted apart (the repository grew a
configurable keyboard-layout pair the installed copy never got), and every fix
had to be applied twice or it silently only reached one of them.

Translating strings at runtime instead means there is exactly one copy of the
logic. LOCALES already existed for reading Name[ru] out of .desktop files, so
the same detection is reused here rather than inventing a second mechanism.

Adding a language: add a dict under its two-letter code. Missing keys fall back
to English, so a partial translation is better than none and never crashes.
"""
from __future__ import annotations

import os

DEFAULT_LANG = "en"


def _locales():
    """ru_RU.UTF-8 → ['ru_RU', 'ru']"""
    lang = os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    lang = lang.split(".")[0].split("@")[0]
    if not lang or lang in ("C", "POSIX"):
        return []
    out = [lang]
    if "_" in lang:
        out.append(lang.split("_")[0])
    return out


LOCALES = _locales()

STRINGS = {
    "en": {
        # apps
        "back": "Back",
        "back_meta": "back up",
        "folder_not_found": 'Folder "{name}" not found',
        "empty": "Empty",
        "nothing_to_pin": "Nothing to pin here",
        "not_pinned": "That application is not pinned",
        "only_pinned_move": "Only pinned entries can be moved",
        "at_the_end": "Already at the end",
        "pinned": '"{name}" pinned',
        "unpinned": '"{name}" unpinned',
        "hint_root": "Ctrl+P unpin · Ctrl+Alt+↑↓ reorder",
        "hint_folder": "Ctrl+P pin · Alt+← back",
        "error": "Hub error: {error}",
        "error_row": "Error — run the hub from a terminal for details",
        # sections
        "sec_clipboard": "Clipboard",
        "sec_clipboard_meta": "clipboard cliphist copy paste buffer history",
        "sec_wallpaper": "Wallpaper",
        "sec_wallpaper_meta": "wallpaper background picture image",
        "sec_animations": "Animations",
        "sec_animations_meta": "animations motion effects preset dissolve",
        "sec_windows": "Windows",
        "sec_windows_meta": "windows switch focus alt-tab",
        "sec_emoji": "Emoji",
        "sec_emoji_meta": "emoji symbols smiley unicode",
        "sec_screenshot": "Screenshot",
        "sec_screenshot_meta": "screenshot screen capture grab",
        "sec_power": "Power",
        "sec_power_meta": "power shutdown reboot suspend logout lock",
        # clipboard
        "clip_empty": "Clipboard history is empty",
        "clip_binary": "[binary data, {size}]",
        "clip_hint": "Enter — copy · Ctrl+X — delete entry",
        "clip_deleted": "Entry deleted",
        "clip_unavailable": "cliphist is not installed",
        # windows
        "win_empty": "No open windows",
        "win_special": "special",
        "win_hint": "Enter — focus · Ctrl+X — close",
        "win_closed": '"{name}" closed',
        # emoji
        "emoji_hint": "Enter — copy to clipboard",
        "emoji_copied": '{char} copied',
        "emoji_missing": "Emoji database not found",
        # screenshot
        "shot_area": "Region",
        "shot_area_meta": "region area select crop part",
        "shot_screen": "Whole screen",
        "shot_screen_meta": "screen full whole display everything",
        "shot_hint": "The hub closes first, then you select",
        # power
        "power_lock": "Lock",
        "power_suspend": "Suspend",
        "power_hibernate": "Hibernate",
        "power_logout": "Log out",
        "power_reboot": "Reboot",
        "power_poweroff": "Shut down",
        "power_hint": "Irreversible actions ask for confirmation",
        "power_confirm": "{action} — are you sure?",
        "power_no": "No, go back",
        "power_yes": "Yes, {action}",
        # animations
        "anim_hint": "Enter — apply · Ctrl+Alt+Space — live preview",
        "anim_active": "active now",
        "anim_applied": 'Preset "{name}" applied',
        "anim_none": "No presets found",
    },
    "ru": {
        # apps
        "back": "Назад",
        "back_meta": "назад back up",
        "folder_not_found": "Папка «{name}» не найдена",
        "empty": "Пусто",
        "nothing_to_pin": "Здесь нечего закреплять",
        "not_pinned": "Это приложение не закреплено",
        "only_pinned_move": "Двигать можно только закреплённые",
        "at_the_end": "Дальше некуда",
        "pinned": "«{name}» закреплено",
        "unpinned": "«{name}» откреплено",
        "hint_root": "Ctrl+P открепить · Ctrl+Alt+↑↓ переставить",
        "hint_folder": "Ctrl+P закрепить · Alt+← назад",
        "error": "Ошибка хаба: {error}",
        "error_row": "Ошибка — запустите хаб из терминала, чтобы увидеть подробности",
        # sections
        "sec_clipboard": "Буфер обмена",
        "sec_clipboard_meta": "буфер обмена clipboard cliphist копировать вставить история",
        "sec_wallpaper": "Обои",
        "sec_wallpaper_meta": "обои wallpaper фон картинка заставка",
        "sec_animations": "Анимации",
        "sec_animations_meta": "анимации animations движение эффекты пресет распад",
        "sec_windows": "Окна",
        "sec_windows_meta": "окна windows переключить фокус",
        "sec_emoji": "Эмодзи",
        "sec_emoji_meta": "эмодзи emoji символы смайлы юникод значки",
        "sec_screenshot": "Скриншот",
        "sec_screenshot_meta": "скриншот снимок экрана screenshot",
        "sec_power": "Питание",
        "sec_power_meta": "питание power выключить перезагрузка сон выход блокировка",
        # clipboard
        "clip_empty": "История буфера пуста",
        "clip_binary": "[двоичные данные, {size}]",
        "clip_hint": "Enter — скопировать · Ctrl+X — удалить запись",
        "clip_deleted": "Запись удалена",
        "clip_unavailable": "cliphist не установлен",
        # windows
        "win_empty": "Открытых окон нет",
        "win_special": "спец",
        "win_hint": "Enter — перейти · Ctrl+X — закрыть",
        "win_closed": "«{name}» закрыто",
        # emoji
        "emoji_hint": "Enter — скопировать в буфер",
        "emoji_copied": "{char} скопировано",
        "emoji_missing": "База эмодзи не найдена",
        # screenshot
        "shot_area": "Область",
        "shot_area_meta": "область выделить часть кусок region area",
        "shot_screen": "Весь экран",
        "shot_screen_meta": "весь экран целиком полный screen full",
        "shot_hint": "Сначала закроется хаб, потом выделяете область",
        # power
        "power_lock": "Заблокировать",
        "power_suspend": "Приостановить",
        "power_hibernate": "Гибернация",
        "power_logout": "Выйти из системы",
        "power_reboot": "Перезагрузить",
        "power_poweroff": "Выключить",
        "power_hint": "Необратимые действия спросят подтверждение",
        "power_confirm": "{action} — точно?",
        "power_no": "Нет, вернуться",
        "power_yes": "Да, {action}",
        # animations
        "anim_hint": "Enter — применить · Ctrl+Alt+Пробел — показать вживую",
        "anim_active": "сейчас активен",
        "anim_applied": "Пресет «{name}» применён",
        "anim_none": "Пресеты не найдены",
    },
}


def _pick_lang():
    for loc in LOCALES:
        code = loc.split("_")[0]
        if code in STRINGS:
            return code
    return DEFAULT_LANG


LANG = _pick_lang()


def t(key, **kwargs):
    """Translate. Falls back to English, then to the key itself."""
    table = STRINGS.get(LANG, {})
    text = table.get(key)
    if text is None:
        text = STRINGS[DEFAULT_LANG].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
