"""SL101 physical keyboard mapping regressions (Nura Sway + keyd)."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIRROR = ROOT / "docs/sl101-device-config"

ALTGR_MAP = {
    "w": "G-102nd",
    "e": "102nd",
    "r": "S-102nd",
    "j": "kprightparen",
    "d": "G-8",
    "s": "G-7",
    "k": "G-9",
    "l": "G-0",
    "f": "kpleftparen",
    ",": "102nd",
    ".": "S-102nd",
    "m": "G-102nd",
    "/": "S-7",
    "right": "end",
    "left": "home",
}


def parse_keyd(text):
    result = {}
    section = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            result[section] = {}
        elif "=" in line:
            key, value = (x.strip() for x in line.split("=", 1))
            result[section][key] = value
        else:
            # keyd's [ids] device identifiers are bare lines.
            result[section][line] = None
    return result


class KeydSwayMappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keyd = parse_keyd((MIRROR / "etc/keyd/sl101.conf").read_text())
        cls.sway = (MIRROR / "home/user/.config/sway/config").read_text()

    def test_main_physical_modifiers(self):
        self.assertEqual(self.keyd["main"]["capslock"], "layer(control)")
        self.assertEqual(self.keyd["main"]["leftcontrol"], "layer(sl101_lctrl)")
        self.assertEqual(self.keyd["main"]["rightalt"], "layer(altgr)")
        self.assertNotIn("meta", self.keyd)
        self.assertEqual(self.keyd["sl101_lctrl:C"], {})

    def test_altgr_workstation_layout(self):
        self.assertEqual(self.keyd["altgr:G"], ALTGR_MAP)

    def test_vt_digit_chords(self):
        self.assertEqual(
            self.keyd["sl101_lctrl+altgr"],
            {str(n): f"C-A-f{n}" for n in range(1, 10)},
        )

    def test_sway_workspace_and_vt_bindings(self):
        # NuraLoumi owns the Super+digits selections; VT escape remains in keyd.
        self.assertIn(
            "set $ws_picker /usr/local/bin/nuraloumi-sway-workspace-switcher\n",
            self.sway,
        )
        for n in range(1, 10):
            with self.subTest(n=n):
                self.assertIn(
                    f"bindsym --no-repeat $mod+{n} exec --no-startup-id $ws_picker {n}\n",
                    self.sway,
                )
                self.assertNotIn(f"bindsym $mod+{n} workspace number {n}\n", self.sway)
                self.assertIn(
                    f"bindsym $mod+Shift+{n} move container to workspace number {n}\n",
                    self.sway,
                )
                self.assertIn(
                    f"bindsym Ctrl+Mod1+F{n} exec sudo /usr/local/bin/sl101-chvt {n}\n",
                    self.sway,
                )
        for key in ("Super_L", "Super_R"):
            self.assertIn(
                f"bindsym --release --no-repeat {key} "
                "exec --no-startup-id $ws_picker --release\n",
                self.sway,
            )
        self.assertIn("bindsym $mod+0 workspace number 10\n", self.sway)

if __name__ == "__main__":
    unittest.main()
