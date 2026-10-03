import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sl101_battery", ROOT / "scripts/sl101-battery.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


class BatteryTests(unittest.TestCase):
    def test_collect_sbs_and_mains(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bat = root / "sbs-5-000b"
            bat.mkdir()
            (bat / "type").write_text("Battery\n")
            (bat / "status").write_text("Charging\n")
            (bat / "capacity").write_text("52\n")
            (bat / "temp").write_text("277\n")
            (bat / "charge_now").write_text("1776000\n")
            (bat / "model_name").write_text("EP10222\n")

            ac = root / "gpio-charger"
            ac.mkdir()
            (ac / "type").write_text("Mains\n")
            (ac / "online").write_text("1\n")

            got = mod.collect(root)
            self.assertEqual(got["batteries"][0]["capacity_percent"], 52)
            self.assertEqual(got["batteries"][0]["temperature_c"], 27.7)
            self.assertEqual(got["batteries"][0]["charge_now_ah"], 1.776)
            self.assertEqual(got["external_power"][0]["online"], 1)

    def test_missing_optional_fields_are_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bat = root / "BAT0"
            bat.mkdir()
            (bat / "type").write_text("Battery\n")
            got = mod.collect(root)["batteries"][0]
            self.assertNotIn("capacity_percent", got)
            self.assertEqual(got["name"], "BAT0")


if __name__ == "__main__":
    unittest.main()
