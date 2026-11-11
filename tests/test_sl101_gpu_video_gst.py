# tests/test_sl101_gpu_video_gst.py
"""Host-only contract tests: no hardware, network or desktop mutation."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "scripts/sl101-gpu-video-gst.py"
spec = importlib.util.spec_from_file_location("sl101_gpu_video_gst", PLAYER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StrictGPUVideo(unittest.TestCase):
    def test_no_cpu_video_sink_or_converter(self):
        for memory in ("system", "dmabuf"):
            argv = module.pipeline_args(Path("/example/clip.mp4"), memory, "none")
            self.assertIn("v4l2slh264dec", argv)
            for element in ("glupload", "glcolorconvert", "glimagesink"):
                self.assertIn(element, argv)
            self.assertIn("video/x-raw(memory:GLMemory),format=RGBA", argv)
            for forbidden in ("videoconvert", "videobox", "waylandsink",
                              "kmssink", "avdec_h264", "decodebin", "autovideosink"):
                self.assertNotIn(forbidden, argv)
            self.assertNotIn("sh", argv)
            self.assertNotIn("-c", argv)

    def test_memory_policy_explicit(self):
        self.assertIn("video/x-raw(memory:DMABuf),format=DMA_DRM",
                      module.pipeline_args(Path("video.mp4"), "dmabuf", "none"))
        self.assertIn("video/x-raw,format=I420",
                      module.pipeline_args(Path("video.mp4"), "system", "none"))
        with self.assertRaises(module.GateError):
            module.pipeline_args(Path("video.mp4"), "auto", "none")

    def test_audio_still_has_fixed_decoder(self):
        argv = module.pipeline_args(Path("safe.mp4"), "system", "pulsesink")
        self.assertIn("aacparse", argv)
        self.assertIn("avdec_aac", argv)
        self.assertIn("pulsesink", argv)
        self.assertNotIn("decodebin", argv)

    def test_env_refuses_software_or_different_gl_platform(self):
        from unittest.mock import patch
        for override in ({"LIBGL_ALWAYS_SOFTWARE": "1"},
                         {"GALLIUM_DRIVER": "softpipe"},
                         {"MESA_LOADER_DRIVER_OVERRIDE": "swrast"},
                         {"GST_GL_PLATFORM": "glx"},
                         {"GST_GL_API": "opengl"}):
            with self.subTest(override=override), patch.dict(module.os.environ, override, clear=True):
                with self.assertRaises(module.GateError):
                    module.gpu_environment("/run/user/1000", "wayland-0")
        with patch.dict(module.os.environ, {}, clear=True):
            env = module.gpu_environment("/run/user/1000", "wayland-0")
        self.assertEqual(env["GST_GL_API"], "gles2")
        self.assertEqual(env["GST_GL_PLATFORM"], "egl")
        self.assertEqual(env["MESA_LOADER_DRIVER_OVERRIDE"], "grate")

    def test_kms_refused_even_with_dry_run(self):
        result = subprocess.run([sys.executable, str(PLAYER), "--mode=kms",
                                 "--dry-run", "/tmp/clip.mp4"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not qualified", result.stderr)

    def test_dry_run_has_no_real_device_dependencies(self):
        result = subprocess.run([sys.executable, str(PLAYER), "--memory=dmabuf",
                                 "--dry-run", "/tmp/a b ' ; .mp4"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertFalse(out["device_qualified"])
        self.assertEqual(out["command_argv"][5], "location=/tmp/a b ' ; .mp4")
        self.assertNotIn("videoconvert", out["command_argv"])

    def test_kernel_pin(self):
        self.assertTrue(module.KERNEL_RE.fullmatch("7.0.1-postmarketos-grate-dmavde1"))
        self.assertTrue(module.KERNEL_RE.fullmatch("7.0.1-postmarketos-grate-dmavde1-minus-cma"))
        self.assertFalse(module.KERNEL_RE.fullmatch("7.0.1-postmarketos-grate"))
        self.assertFalse(module.KERNEL_RE.fullmatch("7.2.6-arch2-1"))

    def test_exact_hardware_identity_gate(self):
        host, sd, emmc = module.IDENTITY_106
        module.verify_identity(host, "7.0.1-postmarketos-grate-dmavde1", sd, emmc)
        for values in ((host, "7.0.1-postmarketos-grate", sd, emmc),
                       (host, "7.0.1-postmarketos-grate-dmavde1", "bad", emmc),
                       ("sltwrpbootdebian", "7.0.1-postmarketos-grate-dmavde1", sd, emmc)):
            with self.assertRaises(module.GateError):
                module.verify_identity(*values)

    def test_no_host_file_mutation_when_dry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "would-be-evidence"
            x = subprocess.run([sys.executable, str(PLAYER), "--dry-run",
                                "--evidence-dir", str(p), "/nonexistent.mp4"],
                               capture_output=True)
            self.assertEqual(x.returncode, 0)
            self.assertFalse(p.exists())


if __name__ == "__main__":
    unittest.main()
