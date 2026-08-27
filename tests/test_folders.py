"""
Folder definitions and the rofi script protocol.

folders.conf is hand-edited, so it must survive being hand-edited badly. And
every line written to stdout is parsed by rofi positionally — a stray newline
or separator byte in an application's name would shift the whole row.
"""
import launcher


def test_the_shipped_default_parses(tmp_path, monkeypatch):
    conf = tmp_path / "folders.conf"
    conf.write_text(launcher.DEFAULT_FOLDERS)
    monkeypatch.setattr(launcher, "FOLDERS_FILE", conf)
    folders = launcher.load_folders()
    assert [f["name"] for f in folders][-1] == "All applications"
    assert any("@all" in f["items"] for f in folders)


def test_a_missing_file_falls_back_to_the_default(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "FOLDERS_FILE", tmp_path / "nope.conf")
    assert launcher.load_folders()


def test_section_order_is_preserved(tmp_path, monkeypatch):
    conf = tmp_path / "folders.conf"
    conf.write_text("[Zebra]\n@all\n\n[Apple]\n@all\n\n[Middle]\n@all\n")
    monkeypatch.setattr(launcher, "FOLDERS_FILE", conf)
    assert [f["name"] for f in launcher.load_folders()] == ["Zebra", "Apple", "Middle"]


def test_an_icon_directive_is_read(tmp_path, monkeypatch):
    conf = tmp_path / "folders.conf"
    conf.write_text("[Tools]\n@icon: applications-utilities\napp.desktop\n")
    monkeypatch.setattr(launcher, "FOLDERS_FILE", conf)
    assert launcher.load_folders()[0]["icon"] == "applications-utilities"


APPS = {
    "alpha.desktop": {"name": "Alpha", "categories": ["Development"], "terminal": False},
    "beta.desktop":  {"name": "Beta",  "categories": ["Network"],     "terminal": False},
    "gamma.desktop": {"name": "Gamma", "categories": ["Development"], "terminal": False},
}


def test_a_category_directive_collects_that_category():
    ids = launcher.resolve_folder({"items": ["@category: Development"]}, APPS, {})
    assert set(ids) == {"alpha.desktop", "gamma.desktop"}


def test_all_collects_everything():
    ids = launcher.resolve_folder({"items": ["@all"]}, APPS, {})
    assert set(ids) == set(APPS)


def test_an_exclusion_removes_an_entry():
    ids = launcher.resolve_folder({"items": ["@all", "-beta.desktop"]}, APPS, {})
    assert "beta.desktop" not in ids
    assert len(ids) == 2


def test_an_exclusion_applies_regardless_of_line_order():
    ids = launcher.resolve_folder({"items": ["-beta.desktop", "@all"]}, APPS, {})
    assert "beta.desktop" not in ids


def test_an_entry_that_does_not_exist_is_ignored():
    ids = launcher.resolve_folder({"items": ["alpha.desktop", "ghost.desktop"]}, APPS, {})
    assert ids == ["alpha.desktop"]


def test_a_named_entry_is_not_duplicated_by_a_category():
    ids = launcher.resolve_folder({"items": ["alpha.desktop", "@category: Development"]}, APPS, {})
    assert ids.count("alpha.desktop") == 1


def test_usage_counts_order_the_all_folder():
    """"All applications" puts what you actually launch at the top."""
    ids = launcher.resolve_folder({"items": ["@all"]}, APPS,
                                  {"gamma.desktop": 50, "alpha.desktop": 1})
    assert ids[0] == "gamma.desktop"


def test_a_category_folder_keeps_a_stable_order():
    """
    A themed folder is sorted by name, not by usage: its whole point is that an
    entry stays where you last saw it, so the muscle memory keeps working.
    """
    ids = launcher.resolve_folder({"items": ["@category: Development"]}, APPS,
                                  {"gamma.desktop": 50, "alpha.desktop": 1})
    assert ids == ["alpha.desktop", "gamma.desktop"]


# --- the rofi script protocol -------------------------------------------

def test_a_newline_in_a_row_cannot_break_the_protocol(capsys):
    launcher.emit_row("first\nsecond")
    out = capsys.readouterr().out
    assert out.count("\n") == 1, "a row must occupy exactly one line"


def test_a_separator_byte_in_a_row_is_neutralised(capsys):
    launcher.emit_row(f"name{launcher.US}injected{launcher.NUL}more")
    out = capsys.readouterr().out.rstrip("\n")
    assert launcher.NUL not in out
    assert launcher.US not in out


def test_a_directive_is_emitted_in_the_documented_shape(capsys):
    launcher.emit_directive("prompt", "Apps")
    out = capsys.readouterr().out
    assert out == f"{launcher.NUL}prompt{launcher.US}Apps\n"


def test_row_options_are_separated_correctly(capsys):
    launcher.emit_row("Row", info="dir:Test", meta="test")
    out = capsys.readouterr().out.rstrip("\n")
    head, _, tail = out.partition(launcher.NUL)
    assert head == "Row"
    assert tail.split(launcher.US) == ["info", "dir:Test", "meta", "test"]
