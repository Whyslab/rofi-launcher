"""
Applications: .desktop scanning, folders, pinned entries, launching.

This is the original rofi-launcher, moved under the hub unchanged in behaviour.
Only two things were taken out of it: the text it shows (now in strings.py, so
the English and Russian copies stop being two forks of one file) and the raw
protocol writing (now in rows.py, shared with every other section).
"""
from __future__ import annotations

import configparser
import html
import json
import locale
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from ..rows import ARROW, GLYPH_FOLDER, MARK_PINNED, back_row, dim, note_row
from ..strings import LOCALES, t

HOME = Path.home()
CFG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "rofi-launcher"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "rofi-launcher"
FOLDERS_FILE = CFG_DIR / "folders.conf"
FAVORITES_FILE = CFG_DIR / "favorites.list"
USAGE_FILE = CACHE_DIR / "usage.json"

TERMINAL = os.environ.get("ROFI_LAUNCHER_TERMINAL", "kitty")

# Field codes the desktop entry spec fills in; they have no place in argv.
FIELD_CODES_DROP = {"%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%v", "%m", "%i"}


# ─────────────────────── reading .desktop files ───────────────────────

# Two keyboard layouts, character by character, in the same physical key order.
# This is what lets a search typed in the wrong layout still find the app: with
# the default pair, typing "ghjdjlybr" finds Thunar and "ntktuhfv" finds Telegram.
#
# To use a different pair of layouts, set both ROFI_LAUNCHER_LAYOUT_PRIMARY and
# ROFI_LAUNCHER_LAYOUT_SECONDARY to the same keys in the same order. Setting
# either to an empty string switches the behaviour off.
#
# They are two separate variables rather than one colon-separated value on
# purpose: ":" is itself a key on the keyboard, and appears in the default
# primary layout below.
_DEFAULT_PRIMARY = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~"
_DEFAULT_SECONDARY = "йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ"


def _layout_tables():
    primary = os.environ.get("ROFI_LAUNCHER_LAYOUT_PRIMARY", _DEFAULT_PRIMARY)
    secondary = os.environ.get("ROFI_LAUNCHER_LAYOUT_SECONDARY", _DEFAULT_SECONDARY)
    if not primary or not secondary:
        return []
    if len(primary) != len(secondary):
        # A mismatched pair would map characters onto the wrong keys, turning a
        # search into gibberish. Doing nothing is the better failure.
        return []
    return [str.maketrans(primary, secondary), str.maketrans(secondary, primary)]


_LAYOUT_TABLES = _layout_tables()


def layout_variants(text):
    """The same text as it would be typed in the other layout, both directions."""
    out = []
    for table in _LAYOUT_TABLES:
        swapped = text.translate(table)
        if swapped != text:
            out.append(swapped)
    return out


def _data_dirs():
    home = os.environ.get("XDG_DATA_HOME") or str(HOME / ".local/share")
    # XDG_DATA_DIRS is empty here — fall back to the spec default.
    dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [home] + [d for d in dirs.split(":") if d]


def _localized(sec, key):
    for suffix in LOCALES:
        val = sec.get(f"{key}[{suffix}]")
        if val:
            return val
    return sec.get(key, "")


def _truthy(sec, key):
    return sec.get(key, "").strip().lower() == "true"


def _tryexec_ok(sec):
    cmd = sec.get("TryExec", "").strip()
    if not cmd:
        return True
    if "/" in cmd:
        return os.access(cmd, os.X_OK)
    return shutil.which(cmd) is not None


def _shown_here(sec):
    current = [d for d in (os.environ.get("XDG_CURRENT_DESKTOP") or "").split(":") if d]
    only = [x for x in sec.get("OnlyShowIn", "").split(";") if x]
    if only and not any(d in only for d in current):
        return False
    not_in = [x for x in sec.get("NotShowIn", "").split(";") if x]
    return not (not_in and any(d in not_in for d in current))


def _parse_desktop(path):
    parser = configparser.ConfigParser(
        strict=False, interpolation=None, delimiters=("=",), comment_prefixes=("#",)
    )
    parser.optionxform = str  # Name and Name[ru] must stay case-distinct
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            parser.read_file(fh)
    except (OSError, configparser.Error):
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    sec = parser["Desktop Entry"]

    if sec.get("Type", "Application").strip() != "Application":
        return None
    if _truthy(sec, "NoDisplay") or _truthy(sec, "Hidden"):
        return None
    if not _tryexec_ok(sec) or not _shown_here(sec):
        return None
    exec_line = sec.get("Exec", "").strip()
    if not exec_line:
        return None

    name = _localized(sec, "Name") or path.stem
    keywords = " ".join(
        filter(None, [_localized(sec, "Keywords"), sec.get("Keywords", "")])
    ).replace(";", " ")
    try:
        exec_base = os.path.basename(shlex.split(exec_line)[0])
    except ValueError:
        exec_base = ""

    meta_parts = [
        name, sec.get("Name", ""), _localized(sec, "GenericName"),
        sec.get("GenericName", ""), _localized(sec, "Comment"),
        keywords, exec_base, path.stem,
    ]
    # Plus the wrong-layout spelling, so searching works without switching layout.
    for part in [name, sec.get("Name", ""), exec_base, path.stem]:
        if part:
            meta_parts.extend(layout_variants(part))
    meta = " ".join(filter(None, meta_parts))

    return {
        "name": name,
        "icon": sec.get("Icon", "").strip(),
        "exec": exec_line,
        "terminal": _truthy(sec, "Terminal"),
        "dbus": _truthy(sec, "DBusActivatable"),
        "path": str(path),
        "workdir": sec.get("Path", "").strip(),
        "categories": [c for c in sec.get("Categories", "").split(";") if c],
        "meta": meta,
    }


def scan_apps():
    """{desktop_id: {...}} — the first occurrence of an id wins (~/.local/share first)."""
    apps = {}
    for base in _data_dirs():
        root = Path(base) / "applications"
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.desktop")):
            desktop_id = str(path.relative_to(root)).replace("/", "-")
            if desktop_id in apps:
                continue
            entry = _parse_desktop(path)
            if entry:
                apps[desktop_id] = entry
    return apps


# ─────────────────────────── state ───────────────────────────

def read_favorites():
    if not FAVORITES_FILE.exists():
        return []
    out = []
    for line in FAVORITES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def write_favorites(ids):
    """An atomic write: rofi may call the script again immediately."""
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FAVORITES_FILE.with_suffix(".list.tmp")
    body = [
        "# Pinned applications. One line = one .desktop entry.",
        "# The order of the lines is the order on the root screen.",
        "# Rewritten on Ctrl+P / Ctrl+Alt+↑↓ — comments below this point are not kept.",
    ] + list(ids)
    tmp.write_text("\n".join(body) + "\n", encoding="utf-8")
    os.replace(tmp, FAVORITES_FILE)


def read_usage():
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bump_usage(desktop_id):
    usage = read_usage()
    usage[desktop_id] = usage.get(desktop_id, 0) + 1
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = USAGE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(usage), encoding="utf-8")
        os.replace(tmp, USAGE_FILE)
    except OSError:
        pass  # a launch counter is not worth breaking a launch over


# ─────────────────────────── folders ───────────────────────────

DEFAULT_FOLDERS = """\
# Launcher folders. The order of the sections is the order on the root screen.
#
#   [Folder name]
#   @icon: <icon name>         optional
#   @category: Development     everything in that .desktop category
#   @all                       every application there is
#   somefile.desktop           one specific application
#   -somefile.desktop          exclude an application
#
# Hand-written lines and @category can be mixed; order within a section is kept.

[Development]
@category: Development

[Internet]
@category: Network
@category: WebBrowser

[Media]
@category: AudioVideo
@category: Audio
@category: Video

[Graphics]
@category: Graphics

[Office]
@category: Office

[Terminal]
@category: TerminalEmulator
@category: ConsoleOnly

[Settings]
@category: Settings
@category: System

[All applications]
@all
"""


def load_folders():
    """[{name, icon, items:[...]}] — in the order they appear in the file."""
    if not FOLDERS_FILE.exists():
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        FOLDERS_FILE.write_text(DEFAULT_FOLDERS, encoding="utf-8")

    folders, current = [], None
    for raw in FOLDERS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = {"name": line[1:-1].strip(), "icon": "", "items": []}
            folders.append(current)
        elif current is not None:
            if line.lower().startswith("@icon:"):
                current["icon"] = line.split(":", 1)[1].strip()
            else:
                current["items"].append(line)
    return [f for f in folders if f["name"]]


def _sort_key(apps, desktop_id):
    name = apps[desktop_id]["name"]
    try:
        return locale.strxfrm(name.casefold())
    except (ValueError, TypeError):
        return name.casefold()


def resolve_folder(folder, apps, usage):
    """A folder's directives → an ordered list of desktop ids."""
    result, excluded = [], set()

    def add(desktop_id):
        if desktop_id in apps and desktop_id not in result:
            result.append(desktop_id)

    for item in folder["items"]:
        if item.startswith("-"):
            excluded.add(item[1:].strip())
        elif item.lower() == "@all":
            ids = sorted(apps, key=lambda i: _sort_key(apps, i))
            ids.sort(key=lambda i: -usage.get(i, 0))  # most-launched first
            for i in ids:
                add(i)
        elif item.lower().startswith("@category:"):
            cat = item.split(":", 1)[1].strip()
            ids = [i for i in apps if cat in apps[i]["categories"]]
            for i in sorted(ids, key=lambda i: _sort_key(apps, i)):
                add(i)
        else:
            add(item)

    return [i for i in result if i not in excluded]


# ─────────────────────────── launching ───────────────────────────

def _strip_field_codes(exec_line, app):
    try:
        tokens = shlex.split(exec_line)
    except ValueError:
        tokens = exec_line.split()
    argv = []
    for token in tokens:
        if token in FIELD_CODES_DROP:
            continue
        token = token.replace("%c", app["name"]).replace("%k", app["path"])
        token = token.replace("%%", "%")
        argv.append(token)
    return argv


def launch(app, desktop_id):
    """
    Terminal=false → gio launch: it handles field codes, Path=, startup
    notification and DBusActivatable, none of which is worth reimplementing.
    Terminal=true  → build argv ourselves: GLib keeps its own list of known
    terminals, and a terminal outside it makes gio launch fail with
    "Unable to find terminal required for application".
    """
    if app["terminal"]:
        argv = [TERMINAL, "-e"] + _strip_field_codes(app["exec"], app)
    else:
        argv = ["gio", "launch", app["path"]]

    workdir = app["workdir"] if app["workdir"] and os.path.isdir(app["workdir"]) else None
    try:
        subprocess.Popen(
            argv, cwd=workdir, start_new_session=True, close_fds=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        if not app["terminal"]:  # no gio, or it failed — parse Exec ourselves
            subprocess.Popen(
                _strip_field_codes(app["exec"], app), cwd=workdir,
                start_new_session=True, close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            raise
    bump_usage(desktop_id)


# ─────────────────────────── rows ───────────────────────────

def app_row(desktop_id, app, pinned):
    label = html.escape(app["name"])
    if pinned:
        label += "  " + dim(MARK_PINNED)
    return (desktop_id, {
        "display": label,
        "meta": app["meta"],
        "info": f"app:{desktop_id}",
        "icon": app["icon"] or "application-x-executable",
    })


def pinned_rows(apps, favorites):
    """The pinned applications, in the order the favorites file lists them."""
    return [
        app_row(i, apps[i], pinned=False)
        for i in favorites
        if i in apps
    ]


def folder_rows(folders):
    return [
        (f"dir:{f['name']}", {
            "display": f"{dim(GLYPH_FOLDER)}  {html.escape(f['name'])}  {dim(ARROW)}",
            "meta": f["name"],
            "info": f"dir:{f['name']}",
        })
        for f in folders
    ]


def build_folder(name, apps, folders, favorites):
    rows = [back_row(t("back"), t("back_meta"))]

    folder = next((f for f in folders if f["name"] == name), None)
    if folder is None:
        rows.append(note_row(t("folder_not_found", name=name)))
        return rows

    ids = resolve_folder(folder, apps, read_usage())
    if not ids:
        rows.append(note_row(t("empty")))
    for desktop_id in ids:
        rows.append(app_row(desktop_id, apps[desktop_id], pinned=desktop_id in favorites))
    return rows


# ─────────────────────────── hotkey actions ───────────────────────────

def hotkey_pin(desktop_id, apps, favorites):
    """A toggle. Ctrl+Shift+P depends on the layout more heavily (an uppercase
    keysym), so unpinning has to be possible with plain Ctrl+P alone."""
    if not desktop_id or desktop_id not in apps:
        return favorites, t("nothing_to_pin")
    name = apps[desktop_id]["name"]
    if desktop_id in favorites:
        favorites.remove(desktop_id)
        write_favorites(favorites)
        return favorites, t("unpinned", name=name)
    favorites.append(desktop_id)
    write_favorites(favorites)
    return favorites, t("pinned", name=name)


def hotkey_unpin(desktop_id, apps, favorites):
    if not desktop_id or desktop_id not in favorites:
        return favorites, t("not_pinned")
    favorites.remove(desktop_id)
    write_favorites(favorites)
    name = apps[desktop_id]["name"] if desktop_id in apps else desktop_id
    return favorites, t("unpinned", name=name)


def hotkey_move(desktop_id, favorites, delta):
    if not desktop_id or desktop_id not in favorites:
        return favorites, t("only_pinned_move")
    old = favorites.index(desktop_id)
    new = max(0, min(len(favorites) - 1, old + delta))
    if new == old:
        return favorites, t("at_the_end")
    favorites.insert(new, favorites.pop(old))
    write_favorites(favorites)
    return favorites, None


__all__ = [
    "CACHE_DIR", "CFG_DIR", "FAVORITES_FILE", "FOLDERS_FILE", "USAGE_FILE",
    "app_row", "build_folder", "folder_rows", "hotkey_move", "hotkey_pin",
    "hotkey_unpin", "launch", "layout_variants", "load_folders", "pinned_rows",
    "read_favorites", "read_usage", "resolve_folder", "scan_apps",
    "write_favorites",
]
