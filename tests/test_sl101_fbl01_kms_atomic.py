import pathlib
import unittest
S = (pathlib.Path(__file__).resolve().parents[1] / "scripts/sl101-fbl01-kms-atomic-capture.sh").read_text()
class TestAtomicCapture(unittest.TestCase):
    def test_target(self):
        self.assertIn("user@192.168.23.106", S)
        self.assertIn("7.0.1-postmarketos-grate", S)
        self.assertIn("ASUS Eee Pad Slider SL101", S)
    def test_debug_restoration(self):
        self.assertIn('old=$(cat /sys/module/drm/parameters/debug)', S)
        self.assertIn('printf "%s\\n" "$old" > /sys/module/drm/parameters/debug', S)
        self.assertIn("trap restore EXIT HUP INT TERM", S)
    def test_trace_bound(self):
        self.assertIn("timeout -s TERM -k 5 75", S)
        self.assertIn("strace -f -tt -v -s 256 -e trace=ioctl", S)
        self.assertIn("sl101-kms-run --timeout 35 --", S)
        self.assertIn("DRY RUN", S)
