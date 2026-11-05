"""Host-only static gate for isolated SL101 input mount namespace smoke."""
from pathlib import Path
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/sl101-cog-input-private-ns-smoke.sh"


class PrivateNamespaceSmokeTest(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(["sh", "-n", str(SOURCE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_identity_and_no_browser(self):
        script = SOURCE.read_text()
        for required in (
            '"sl101-nura"', '"7.0.1-postmarketos-grate"',
            '"035344534c31323880ac79a543010300"',
            '"SL101_DESKTOP_RENDERER=grate"',
            "pgrep -xo labwc", "pgrep -xo cog",
            "unshare --mount --fork", "mount --make-rprivate /",
            'this_ns', 'SL101_INPUT_PARENT_NS',
            "PASS_NO_HOST_MOUNT_LEAK", "trap cleanup EXIT",
        ):
            with self.subTest(required=required):
                self.assertIn(required, script)
        self.assertLess(script.index("pgrep -xo cog"),
                        script.index("unshare --mount --fork"))

    def test_no_installed_launcher_or_raw_input_read(self):
        script = SOURCE.read_text()
        self.assertNotIn("sl101-cog-kms-session", script)
        self.assertNotIn("sl101-cog-kms-launch", script)
        self.assertNotIn("chroot ", script)
        self.assertNotIn("kill ", script)
        self.assertNotIn("cat /dev/input", script)
        self.assertNotIn("dd if=/dev/input", script)
        self.assertNotIn("mount --rbind /dev", script)
        self.assertIn("setpriv --reuid=1000 --regid=1000 --groups 23", script)


if __name__ == "__main__":
    unittest.main()
