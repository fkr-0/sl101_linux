"""Static regression gate for the SL101 Sway/NuraLoumi workspace switcher integration.

This suite does not launch Sway, switch a VT, or interact with a live desktop.
"""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SWAY = ROOT / "docs/sl101-device-config/home/user/.config/sway/config"
KEYD = ROOT / "docs/sl101-device-config/etc/keyd/sl101.conf"


class SwayWorkspaceSwitcherDeployTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sway = SWAY.read_text()
        cls.keyd = KEYD.read_text()

    def test_each_super_digit_only_dispatches_to_switcher(self):
        for digit in range(1, 10):
            with self.subTest(digit=digit):
                matches = re.findall(
                    rf"^bindsym[^\n]*\$mod\+{digit} (.+)$",
                    self.sway,
                    re.M,
                )
                self.assertEqual(
                    matches,
                    [f"exec --no-startup-id $ws_picker {digit}"],
                )
        self.assertIn(
            "set $ws_picker /usr/local/bin/nuraloumi-sway-workspace-switcher",
            self.sway,
        )

    def test_super_release_closes_switcher(self):
        for key in ("Super_L", "Super_R"):
            self.assertIn(
                f"bindsym --release --no-repeat {key} "
                "exec --no-startup-id $ws_picker --release",
                self.sway,
            )

    def test_existing_shortcuts_and_vt_recovery_untouched(self):
        for digit in range(1, 10):
            with self.subTest(digit=digit):
                self.assertIn(
                    f"bindsym $mod+Shift+{digit} "
                    f"move container to workspace number {digit}",
                    self.sway,
                )
                self.assertIn(f"{digit} = C-A-f{digit}", self.keyd)
                self.assertIn(
                    f"bindsym Ctrl+Mod1+F{digit} "
                    f"exec sudo /usr/local/bin/sl101-chvt {digit}",
                    self.sway,
                )
        self.assertIn("bindsym $mod+0 workspace number 10", self.sway)
        self.assertIn("[sl101_lctrl+altgr]", self.keyd)
        self.assertIn("bindsym $mod+Shift+r reload", self.sway)
        self.assertIn("exec_always /usr/local/bin/sl101-sway-panel", self.sway)


if __name__ == "__main__":
    unittest.main()
