"""Host-only regression tests for Sway reload's NuraLoumi panel hook."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PANEL_HOOK = ROOT / "docs/sl101-device-config/usr/local/bin/sl101-sway-panel"
SWAY_CONFIG = ROOT / "docs/sl101-device-config/home/user/.config/sway/config"


class SwayPanelReloadTests(unittest.TestCase):
    def test_config_reload_uses_exec_always_panel_hook(self):
        config = SWAY_CONFIG.read_text()
        self.assertIn("bindsym $mod+Shift+r reload", config)
        self.assertIn("exec_always /usr/local/bin/sl101-sway-panel", config)
        self.assertNotIn("exec /opt/nuraloumi/current/nuraloumi-panel", config)

    def test_hook_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(PANEL_HOOK)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_busybox_pgrep_filters_real_uid_without_unsupported_flags(self):
        hook = PANEL_HOOK.read_text()
        self.assertIn("pgrep -x nuraloumi-panel", hook)
        self.assertNotIn("pgrep -u", hook)
        self.assertIn('"/proc/$pid/status"', hook)

    def test_missing_panel_does_not_mutate_desktop(self):
        with tempfile.TemporaryDirectory(prefix="sl101-sway-test-") as temp:
            env = os.environ.copy()
            env.update(
                HOME=temp,
                XDG_RUNTIME_DIR=temp,
                SL101_SWAY_PANEL_BIN=str(Path(temp) / "nonexistent-panel"),
            )
            result = subprocess.run(
                ["sh", str(PANEL_HOOK)], env=env, capture_output=True, text=True, timeout=5
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing executable", result.stderr)

    @unittest.skipUnless(shutil.which("flock"), "flock is required")
    def test_reload_starts_panel_and_releases_lock(self):
        with tempfile.TemporaryDirectory(prefix="sl101-sway-test-") as temp:
            base = Path(temp)
            bindir = base / "bin"
            bindir.mkdir()
            # No host processes are inspected or killed by this test.
            pgrep = bindir / "pgrep"
            pgrep.write_text(chr(10).join(("#!/bin/sh", "exit 1", "")))
            pgrep.chmod(0o755)
            panel = base / "fake-panel"
            panel.write_text(chr(10).join(("#!/bin/sh", 'echo "$*" >> "$SL101_TEST_MARKER"', "sleep 0.8", "")))
            panel.chmod(0o755)
            marker = base / "started"
            env = os.environ.copy()
            env.update(
                HOME=temp,
                XDG_RUNTIME_DIR=temp,
                XDG_STATE_HOME=str(base / "state"),
                SL101_SWAY_PANEL_BIN=str(panel),
                SL101_TEST_MARKER=str(marker),
                PATH=f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            )
            result = subprocess.run(
                ["sh", str(PANEL_HOOK)], env=env, capture_output=True, text=True, timeout=6
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.is_file(), result.stderr)
            self.assertEqual(marker.read_text().splitlines(), ["--live --enable-renderer-switch"])
            lock = base / "sl101-sway-panel.lock"
            self.assertTrue(lock.is_file())
            acquired = subprocess.run(
                ["flock", "-n", str(lock), "true"], capture_output=True, text=True
            )
            self.assertEqual(acquired.returncode, 0, "panel retained reload lock")


if __name__ == "__main__":
    unittest.main()
