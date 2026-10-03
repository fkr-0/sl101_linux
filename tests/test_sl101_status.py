import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sl101_status",
    ROOT / "scripts/sl101-status.py",
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class T(unittest.TestCase):
    def test_meminfo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            (path / "meminfo").write_text(
                "MemTotal: 1000 kB\nMemAvailable: 250 kB\n"
            )
            result = m.meminfo(path)
            self.assertEqual(result["used_bytes"], 750 * 1024)
            self.assertAlmostEqual(result["used_percent"], 75.0)

    def test_power_wifi_bluetooth(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            battery = root / "class/power_supply/BAT"
            battery.mkdir(parents=True)
            (battery / "type").write_text("Battery\n")
            (battery / "capacity").write_text("88\n")
            (battery / "status").write_text("Discharging\n")

            ac = root / "class/power_supply/AC"
            ac.mkdir()
            (ac / "type").write_text("Mains\n")
            (ac / "online").write_text("1\n")

            bluetooth = root / "class/bluetooth/hci0"
            bluetooth.mkdir(parents=True)

            rfkill = root / "class/rfkill/rfkill0"
            rfkill.mkdir(parents=True)
            (rfkill / "type").write_text("bluetooth\n")
            (rfkill / "name").write_text("hci0\n")
            (rfkill / "soft").write_text("0\n")
            (rfkill / "hard").write_text("0\n")

            result = m.power(root)
            self.assertEqual(result["battery"][0]["capacity"], 88)
            self.assertEqual(result["external"][0]["online"], 1)
            self.assertEqual(m.bluetooth(root)["adapters"][0]["name"], "hci0")


if __name__ == "__main__":
    unittest.main()
