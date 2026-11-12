# tests/test_sl101_gstgl_egl_probe.py
"""Host-only guardrail tests. No remote processes, GPU or device touched."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sl101-gstgl-egl-probe.py"
spec = importlib.util.spec_from_file_location("sl101_gstgl_egl_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class GstGLEGLProbeContract(unittest.TestCase):
    def test_dry_run_never_reaches_device(self):
        result = subprocess.run([sys.executable, str(SCRIPT)],
                                capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertFalse(data["device_touched"])
        self.assertFalse(data["accepted"])
        self.assertIn("glupload", data["fixture"])

    def test_fixture_explicit_gpu_only(self):
        for element in ("videotestsrc", "glupload", "glcolorconvert", "glimagesink"):
            self.assertIn(element, probe.FIXTURE)
        for forbidden in ("waylandsink", "videoconvert", "kmssink", "avdec_h264",
                          "decodebin", "autovideosink", "ximagesink"):
            self.assertNotIn(forbidden, probe.FIXTURE)

    def test_env_roundtrip_and_invalid_compositor(self):
        self.assertEqual(probe.parse_env(b"FOO=x=y\0BAR=z\0"), {"FOO": "x=y", "BAR": "z"})
        valid = {
            "WLR_RENDERER": "gles2", "WLR_RENDERER_ALLOW_SOFTWARE": "0",
            "MESA_LOADER_DRIVER_OVERRIDE": "grate",
            "LIBGL_DRIVERS_PATH": str(probe.PREFIX),
            "GBM_BACKENDS_PATH": str(probe.PREFIX / "gbm"),
            "LD_LIBRARY_PATH": "/usr/lib:" + str(probe.PREFIX),
            "LD_PRELOAD": "/usr/local/lib/gr3d_serialize.so",
        }
        self.assertIn("LD_PRELOAD", probe.valid_env(valid))
        for k, bad in (("WLR_RENDERER", "pixman"),
                       ("LIBGL_DRIVERS_PATH", "/lib"),
                       ("LD_PRELOAD", ""),
                       ("GALLIUM_DRIVER", "softpipe")):
            with self.subTest(k=k), self.assertRaises(probe.GateError):
                probe.valid_env({**valid, k: bad})

    def test_dry_run_does_not_create_output(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "never"
            result = subprocess.run([sys.executable, str(SCRIPT),
                                     "--out", str(out)], capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
