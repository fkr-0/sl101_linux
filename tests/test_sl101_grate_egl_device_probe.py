"""Read-only structural checks for the SL101 glibc EGLDevice probe."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "sl101-grate-egl-device-probe.c"


class EGLDeviceProbeTests(unittest.TestCase):
    def test_probe_is_read_only_and_checks_device(self):
        source = PROBE.read_text()
        for call in (
            "gbm_create_device(", "eglGetPlatformDisplayEXT",
            "eglInitialize(", "eglQueryDisplayAttribEXT",
            "eglQueryDeviceStringEXT", "EGL_DEVICE_EXT",
            "EGL_EXT_device_drm", "eglGetError()",
            "eglTerminate(", "gbm_device_destroy(",
        ):
            with self.subTest(call=call):
                self.assertIn(call, source)

    def test_no_graphics_submission_or_device_mutation(self):
        source = PROBE.read_text()
        for prohibited in ("eglSwapBuffers(", "glDraw", "drmModeSetCrtc(",
                           "ioctl(", "system(", "execve("):
            self.assertNotIn(prohibited, source)


if __name__ == "__main__":
    unittest.main()
