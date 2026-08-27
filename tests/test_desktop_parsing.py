"""
Reading .desktop files and turning them into launchable commands.

The desktop entry spec has a lot of ways to say "do not show this" and a lot of
field codes that must not reach argv. Getting either wrong is quiet: an app
missing from the list, or a command that fails with a stray %U in it.
"""
import launcher


def write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body)
    return path


BASIC = """\
[Desktop Entry]
Type=Application
Name=Text Editor
Exec=editor %F
Categories=Utility;TextEditor;
"""


def test_a_basic_entry_is_parsed(tmp_path):
    app = launcher._parse_desktop(write(tmp_path, "editor.desktop", BASIC))
    assert app["name"] == "Text Editor"
    assert app["terminal"] is False
    assert "Utility" in app["categories"]


def test_nodisplay_entries_are_skipped(tmp_path):
    app = launcher._parse_desktop(write(tmp_path, "x.desktop", BASIC + "NoDisplay=true\n"))
    assert app is None


def test_hidden_entries_are_skipped(tmp_path):
    app = launcher._parse_desktop(write(tmp_path, "x.desktop", BASIC + "Hidden=true\n"))
    assert app is None


def test_entries_without_exec_are_skipped(tmp_path):
    body = "[Desktop Entry]\nType=Application\nName=No Exec\n"
    assert launcher._parse_desktop(write(tmp_path, "x.desktop", body)) is None


def test_non_application_types_are_skipped(tmp_path):
    body = "[Desktop Entry]\nType=Link\nName=A Link\nURL=https://example.com\n"
    assert launcher._parse_desktop(write(tmp_path, "x.desktop", body)) is None


def test_a_missing_tryexec_binary_hides_the_entry(tmp_path):
    body = BASIC + "TryExec=/definitely/not/here/binary\n"
    assert launcher._parse_desktop(write(tmp_path, "x.desktop", body)) is None


def test_a_present_tryexec_binary_keeps_the_entry(tmp_path):
    body = BASIC + "TryExec=/bin/sh\n"
    assert launcher._parse_desktop(write(tmp_path, "x.desktop", body)) is not None


def test_a_malformed_file_does_not_raise(tmp_path):
    path = write(tmp_path, "x.desktop", "not a desktop file at all")
    assert launcher._parse_desktop(path) is None


def test_a_terminal_entry_is_marked_as_such(tmp_path):
    app = launcher._parse_desktop(write(tmp_path, "x.desktop", BASIC + "Terminal=true\n"))
    assert app["terminal"] is True


def test_field_codes_are_stripped_from_the_command(tmp_path):
    app = launcher._parse_desktop(write(tmp_path, "x.desktop", BASIC))
    argv = launcher._strip_field_codes(app["exec"], app)
    assert argv == ["editor"]
    assert not any(a.startswith("%") for a in argv)


def test_every_field_code_the_spec_defines_is_dropped(tmp_path):
    body = BASIC.replace("Exec=editor %F", "Exec=editor %f %F %u %U %d %D %n %N %v %m --real")
    app = launcher._parse_desktop(write(tmp_path, "x.desktop", body))
    argv = launcher._strip_field_codes(app["exec"], app)
    assert argv == ["editor", "--real"]


def test_percent_i_expands_to_the_icon_flag(tmp_path):
    body = BASIC.replace("Exec=editor %F", "Exec=editor %i") + "Icon=text-editor\n"
    app = launcher._parse_desktop(write(tmp_path, "x.desktop", body))
    argv = launcher._strip_field_codes(app["exec"], app)
    # %i either expands to --icon <name> or is dropped, but must never survive raw.
    assert "%i" not in argv


def test_a_double_percent_is_left_as_a_literal(tmp_path):
    body = BASIC.replace("Exec=editor %F", "Exec=editor 100%%")
    app = launcher._parse_desktop(write(tmp_path, "x.desktop", body))
    argv = launcher._strip_field_codes(app["exec"], app)
    assert argv[-1] in ("100%", "100%%")


def test_quoted_arguments_survive_parsing(tmp_path):
    body = BASIC.replace("Exec=editor %F", 'Exec=editor --title "My Editor" %F')
    app = launcher._parse_desktop(write(tmp_path, "x.desktop", body))
    argv = launcher._strip_field_codes(app["exec"], app)
    assert "My Editor" in argv
