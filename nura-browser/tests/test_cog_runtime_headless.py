"""Static, side-effect-free audit of the read-only native .106 launcher.

The actual hardware test is separate and must never be dispatched from CI.
"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/qualify-cog-runtime-headless.sh"


class CogRuntimeHeadlessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text()

    def test_posix_shell_syntax(self):
        result = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_stage_fails_without_mount(self):
        # May be run by root in CI: never supply a valid stage.
        result = subprocess.run(
            ["sh", str(SCRIPT), "--preflight",
             "/tmp/nurabrowser-smoke-nonexistent-sentinel",
             "0" * 64],
            capture_output=True, text=True, timeout=5
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("entering private namespace", result.stdout)

    def test_only_private_namespace_mounts(self):
        code = self.script
        self.assertIn('readlink /proc/self/ns/mnt', code)
        self.assertIn('readlink /proc/1/ns/mnt', code)
        self.assertIn("refusing to run --inner in the host mount namespace", code)
        self.assertLess(code.index("mount --make-rprivate /"),
                        code.index('mount --rbind "$root" "$root"'))
        self.assertLess(code.index('mount --rbind "$root" "$root"'),
                        code.index('mount --bind "$stage" "$root/var/tmp"'))
        self.assertIn("unshare --mount --fork --kill-child=SIGKILL", code)
        self.assertIn("timeout -s TERM -k 5 30", code)
        self.assertNotIn("mount --rbind /dev", code)

    def test_no_graphics_or_sandbox_bypass(self):
        code = self.script
        self.assertIn("WPE_PLATFORM=headless", code)
        self.assertIn("LIBGL_ALWAYS_SOFTWARE=1", code)
        self.assertIn("MESA_LOADER_DRIVER_OVERRIDE=swrast", code)
        self.assertIn("--no-control", code)
        self.assertIn("--exit-after-ms=7500", code)
        self.assertIn("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS", code)
        self.assertNotIn("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1", code)
        self.assertNotIn("WPE_PLATFORM=drm", code)

    def test_exact_pinned_abi_and_overlay_hashes(self):
        code = self.script
        self.assertIn("/usr/lib/arm-linux-gnueabihf/libWPEWebKit-2.0.so.1", code)
        self.assertIn("/usr/lib/arm-linux-gnueabihf/libc.so.6", code)
        self.assertIn("/usr/lib/arm-linux-gnueabihf/ld-linux-armhf.so.3", code)
        self.assertIn("libwebp.so.7", code)
        self.assertIn("libsharpyuv.so.0", code)
        self.assertIn('stat -c %u "$stage/state"', code)
        self.assertIn("private /tmp/nurabrowser-smoke-* directory", code)


if __name__ == "__main__":
    unittest.main()
