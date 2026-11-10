"""Host-only tests for Sway/Wayland Cog WebKit extension injection.

Exercise the actual source-snapshot shell fragment in an isolated temporary
root. Never mount, chroot, connect to the device or start Cog.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "docs/sl101-device-config/usr/local/bin/sl101-cog-wpe-root"
ENTER = ROOT / "docs/sl101-device-config/usr/local/libexec/sl101-cog-wpe-enter"


def snapshot_fragment() -> str:
    body = LAUNCHER.read_text()
    start = body.index("SL101_COG_JS_READY=0\n")
    end = body.index("export SL101_COG_JS_READY\n", start) + len("export SL101_COG_JS_READY\n")
    fragment = body[start:end]
    # These shell substitutions only exist inside the test harness.
    # chroot() can read files in the fake directory as uid 1000 would,
    # without invoking a privileged system API.
    prelude = """
root=$1
inject=$2
chroot() {
    childroot=$1
    shift
    for last do :; done
    /bin/cat -- "$childroot$last"
}
"""
    return prelude + fragment + "printf 'READY=%s\\n' \"$SL101_COG_JS_READY\"\n"


class CogWaylandJsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "var/lib").mkdir(parents=True)
        self.extension = self.root / "usr/lib/sl101-cog-extensions"
        self.extension.mkdir(parents=True)
        self.source = self.root / "var/lib/sl101-cog-chrome.js"
        self.source.write_text("window.sl101ChromeReady = true;\n")
        (self.extension / "libsl101-cog-inject.so").write_bytes(b"test-mock")

    def call(self, inject="/var/lib/sl101-cog-chrome.js"):
        return subprocess.run(["sh", "-eu", "-c", snapshot_fragment(), "--",
                               str(self.root), inject],
                              capture_output=True, text=True, check=False)

    def test_shell_syntax(self):
        for p in (LAUNCHER, ENTER):
            completed = subprocess.run(["sh", "-n", str(p)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_snapshot_is_atomic_and_browser_visible(self):
        r = self.call()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("READY=1", r.stdout)
        target = self.extension / "sl101-cog-script.js"
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        self.assertEqual(list(self.extension.glob("*.new")), [])

    def test_no_inject_skips_snapshot(self):
        r = self.call("")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("READY=0", r.stdout)
        self.assertFalse((self.extension / "sl101-cog-script.js").exists())

    def test_missing_extension_refuses_inject(self):
        (self.extension / "libsl101-cog-inject.so").unlink()
        r = self.call()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("extension missing", r.stderr)
        self.assertFalse((self.extension / "sl101-cog-script.js").exists())

    def test_symlinked_source_refused(self):
        self.source.unlink()
        self.source.symlink_to("/etc/passwd")
        r = self.call()
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.extension / "sl101-cog-script.js").exists())

    def test_missing_source_refused(self):
        self.source.unlink()
        self.assertNotEqual(self.call().returncode, 0)

    def test_bad_relative_source_refused(self):
        r = self.call("var/lib/sl101-cog-chrome.js")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("absolute", r.stderr)

    def test_empty_source_refused(self):
        self.source.write_bytes(b"")
        r = self.call()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty", r.stderr)

    def test_both_modes_use_browser_snapshot(self):
        body = ENTER.read_text()
        self.assertIn('injection=${SL101_COG_JS_READY:-0}', body)
        self.assertIn('--web-extensions-dir=/usr/lib/sl101-cog-extensions', body)
        self.assertEqual(body.count('SL101_COG_INJECT_SCRIPT="$inject_path"'), 2)
        self.assertIn("WEBKIT_SKIA_ENABLE_CPU_RENDERING=1", body)
        self.assertIn("--features=-UseDamagingInformationForCompositing", body)
        self.assertIn('LIBGL_ALWAYS_SOFTWARE=1', body)

    def test_no_sandbox_disable_or_host_flash(self):
        combined = LAUNCHER.read_text() + ENTER.read_text()
        for forbidden in ("WEBKIT_DISABLE_SANDBOX", "kexec ", "reboot ", "dd if="):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
