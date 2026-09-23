"""
The hub opens the animations grid in a second rofi and exits. rofi refuses to
start while another instance holds its pid-file lock, so a grid started a
moment too early used to vanish without a trace. The script now waits for the
lock; these tests run it against a stub rofi, never a real window.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "bin" / "hub-animations.sh"

pytestmark = pytest.mark.skipif(shutil.which("flock") is None, reason="needs util-linux flock")


def _run(tmp_path, hold_seconds):
    runtime = tmp_path / "run"
    runtime.mkdir()
    pidfile = runtime / "rofi.pid"
    pidfile.write_text("1\n")
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    marker = tmp_path / "started"
    stub = stub_dir / "rofi"
    stub.write_text(f"#!/bin/sh\ndate +%s.%N > '{marker}'\n")
    stub.chmod(0o755)
    env = dict(os.environ, PATH=f"{stub_dir}:{os.environ['PATH']}", XDG_RUNTIME_DIR=str(runtime))

    holder = None
    if hold_seconds:
        holder = subprocess.Popen(["flock", "-x", str(pidfile), "sleep", str(hold_seconds)])
        time.sleep(0.2)  # let the holder take the lock
    start = time.time()
    subprocess.run(["sh", str(SCRIPT)], env=env, check=True, timeout=10)
    if holder:
        holder.wait()
    return float(marker.read_text()) - start


def test_the_grid_waits_for_the_hub_to_let_go_of_the_lock(tmp_path):
    waited = _run(tmp_path, hold_seconds=1)
    assert waited >= 0.6, "rofi started while the old instance still held the lock"


def test_no_lock_means_no_wait(tmp_path):
    assert _run(tmp_path, hold_seconds=0) < 0.5
