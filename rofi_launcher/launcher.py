#!/usr/bin/env python3
"""
rofi script mode: an application launcher with folders and pinned entries.

Protocol: man rofi-script(5).
  ROFI_RETV=0      — first call
  ROFI_RETV=1      — a row was selected ($1 = its text, ROFI_INFO = its info field)
  ROFI_RETV=10..28 — kb-custom-1..19 (needs use-hot-keys=true)
  ROFI_DATA        — state the script handed to itself on the previous call

Debugging without rofi:
  ROFI_RETV=0 ./launcher.py | cat -v
  ./launcher.py --dump-apps
  ./launcher.py --launch firefox.desktop
"""

import configparser
import contextlib
import html
import json
import locale
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

US = "\x1f"   # separates key/value pairs
NUL = "\0"    # prefixes a directive line, and the options part of a row

HOME = Path.home()
CFG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "rofi-launcher"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "rofi-launcher"
FOLDERS_FILE = CFG_DIR / "folders.conf"
FAVORITES_FILE = CFG_DIR / "favorites.list"
USAGE_FILE = CACHE_DIR / "usage.json"

TERMINAL = os.environ.get("ROFI_LAUNCHER_TERMINAL", "kitty")

GLYPH_SEARCH = ""     # the root prompt; a glyph here needs a font that has it
GLYPH_FOLDER = ""  # a folder
GLYPH_BACK = ""  # the back arrow
MARK_PINNED = "★"
ARROW = "→"
DIM = "#5a5a5a"

# Field codes the desktop entry spec fills in; they have no place in argv.
FIELD_CODES_DROP = {"%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%v", "%m", "%i"}

HINT_ROOT = "Ctrl+P unpin · Ctrl+Alt+↑↓ reorder"
HINT_FOLDER = "Ctrl+P pin · Alt+← back"


# ─────────────────────────── output to rofi ───────────────────────────

def _clean(value):
    """Directives and row options are single-line; a newline would derail rofi."""
    return str(value).replace("\n", " ").replace(NUL, "").replace(US, " ")


def emit_directive(key, value):
    sys.stdout.write(f"{NUL}{_clean(key)}{US}{_clean(value)}\n")


def emit_row(text, **opts):
    line = _clean(text)
    if opts:
        line += NUL + US.join(f"{_clean(k)}{US}{_clean(v)}" for k, v in opts.items())
    sys.stdout.write(line + "\n")


def dim(text):
    return f"<span foreground='{DIM}'>{text}</span>"


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


# ─────────────────────────── rendering ───────────────────────────

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


def build_root(apps, folders, favorites):
    rows = []
    for desktop_id in favorites:
        if desktop_id in apps:
            rows.append(app_row(desktop_id, apps[desktop_id], pinned=False))

    if rows and folders:
        rows.append(("─" * 24, {
            "display": dim("─" * 24), "nonselectable": "true", "meta": "",
        }))

    for folder in folders:
        rows.append((f"dir:{folder['name']}", {
            "display": f"{dim(GLYPH_FOLDER)}  {html.escape(folder['name'])}  {dim(ARROW)}",
            "meta": folder["name"],
            "info": f"dir:{folder['name']}",
        }))
    return rows


def build_folder(name, apps, folders, favorites):
    rows = [("..", {
        "display": f"{dim(GLYPH_BACK)}  {dim('Back')}",
        "meta": "back up",
        "info": "up",
        "permanent": "true",   # stays visible while typing
    })]

    folder = next((f for f in folders if f["name"] == name), None)
    if folder is None:
        rows.append(("!", {"display": dim(f"Folder \"{html.escape(name)}\" not found"),
                           "nonselectable": "true"}))
        return rows

    ids = resolve_folder(folder, apps, read_usage())
    if not ids:
        rows.append(("!", {"display": dim("Empty"), "nonselectable": "true"}))
    for desktop_id in ids:
        rows.append(app_row(desktop_id, apps[desktop_id], pinned=desktop_id in favorites))
    return rows


def render(level, apps, folders, favorites, select_text=None, message=None):
    emit_directive("use-hot-keys", "true")   # without this kb-custom never reaches the script
    emit_directive("markup-rows", "true")
    emit_directive("no-custom", "true")
    emit_directive("data", level)

    if level:
        emit_directive("prompt", f"{GLYPH_FOLDER}  {level}")
        rows = build_folder(level, apps, folders, favorites)
        hint = HINT_FOLDER
    else:
        if GLYPH_SEARCH:
            emit_directive("prompt", GLYPH_SEARCH)
        rows = build_root(apps, folders, favorites)
        hint = HINT_ROOT
    emit_directive("message", dim(message or hint))

    if select_text is not None:
        for index, (text, _) in enumerate(rows):
            if text == select_text:
                emit_directive("keep-selection", "true")
                emit_directive("new-selection", str(index))
                break

    for text, opts in rows:
        emit_row(text, **opts)


# ─────────────────────────── hotkey actions ───────────────────────────

def selected_id(info, argv_text):
    """info is more reliable, but is not guaranteed on kb-custom — the row text is the id."""
    if info.startswith("app:"):
        return info[4:]
    if info.startswith("dir:") or info == "up":
        return None
    return argv_text or None


def hotkey_pin(desktop_id, apps, favorites):
    """A toggle. Ctrl+Shift+P depends on the layout more heavily (an uppercase
    keysym), so unpinning has to be possible with plain Ctrl+P alone."""
    if not desktop_id or desktop_id not in apps:
        return favorites, "Nothing to pin here"
    name = apps[desktop_id]["name"]
    if desktop_id in favorites:
        favorites.remove(desktop_id)
        write_favorites(favorites)
        return favorites, f"\"{name}\" unpinned"
    favorites.append(desktop_id)
    write_favorites(favorites)
    return favorites, f"\"{name}\" pinned"


def hotkey_unpin(desktop_id, apps, favorites):
    if not desktop_id or desktop_id not in favorites:
        return favorites, "That application is not pinned"
    favorites.remove(desktop_id)
    write_favorites(favorites)
    name = apps[desktop_id]["name"] if desktop_id in apps else desktop_id
    return favorites, f"\"{name}\" unpinned"


def hotkey_move(desktop_id, favorites, delta):
    if not desktop_id or desktop_id not in favorites:
        return favorites, "Only pinned entries can be moved"
    old = favorites.index(desktop_id)
    new = max(0, min(len(favorites) - 1, old + delta))
    if new == old:
        return favorites, "Already at the end"
    favorites.insert(new, favorites.pop(old))
    write_favorites(favorites)
    return favorites, None


# ─────────────────────────── entry point ───────────────────────────

def main():
    with contextlib.suppress(locale.Error):
        locale.setlocale(locale.LC_COLLATE, "")

    argv_text = sys.argv[1] if len(sys.argv) > 1 else ""

    if os.environ.get("ROFI_LAUNCHER_DEBUG"):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_DIR / "debug.log", "a", encoding="utf-8") as fh:
                fh.write("RETV={!r} INFO={!r} DATA={!r} argv={!r}\n".format(
                    os.environ.get("ROFI_RETV"), os.environ.get("ROFI_INFO"),
                    os.environ.get("ROFI_DATA"), sys.argv[1:]))
        except OSError:
            pass

    # Manual modes for debugging, outside rofi.
    if argv_text == "--dump-apps":
        apps = scan_apps()
        for desktop_id in sorted(apps, key=lambda i: _sort_key(apps, i)):
            app = apps[desktop_id]
            flags = "T" if app["terminal"] else "-"
            flags += "D" if app["dbus"] else "-"
            print(f"{flags}  {desktop_id:<40} {app['name']}")
        print(f"\ntotal: {len(apps)}")
        return
    if argv_text == "--launch":
        apps = scan_apps()
        desktop_id = sys.argv[2]
        launch(apps[desktop_id], desktop_id)
        return

    retv = int(os.environ.get("ROFI_RETV", "0") or 0)
    info = os.environ.get("ROFI_INFO", "")
    level = os.environ.get("ROFI_DATA", "")

    apps = scan_apps()
    folders = load_folders()
    favorites = read_favorites()

    if retv == 1:
        if info == "up" or argv_text == "..":
            render("", apps, folders, favorites, select_text=f"dir:{level}")
            return
        if info.startswith("dir:"):
            render(info[4:], apps, folders, favorites)
            return
        desktop_id = selected_id(info, argv_text)
        if desktop_id and desktop_id in apps:
            launch(apps[desktop_id], desktop_id)
            return  # empty output → rofi closes
        render(level, apps, folders, favorites)
        return

    if retv >= 10:
        desktop_id = selected_id(info, argv_text)
        message = None
        if retv == 10:      # Ctrl+P
            favorites, message = hotkey_pin(desktop_id, apps, favorites)
        elif retv == 11:    # kb-custom-2 — not bound to anything by default
            favorites, message = hotkey_unpin(desktop_id, apps, favorites)
        elif retv == 12:    # Ctrl+Alt+Up
            favorites, message = hotkey_move(desktop_id, favorites, -1)
        elif retv == 13:    # Ctrl+Alt+Down
            favorites, message = hotkey_move(desktop_id, favorites, +1)
        elif retv == 14:    # Alt+Left / Alt+BackSpace
            render("", apps, folders, favorites, select_text=f"dir:{level}")
            return
        render(level, apps, folders, favorites,
               select_text=desktop_id, message=message)
        return

    render(level, apps, folders, favorites)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # otherwise any bug looks like a successful launch
        emit_directive("message", f"Launcher error: {html.escape(str(exc))}")
        emit_row("Error — run rofi -show apps from a terminal for details",
                 nonselectable="true")
        sys.exit(0)
