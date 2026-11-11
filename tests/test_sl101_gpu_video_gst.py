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

    def test_real_sway_grate_runtime_is_required(self):
        valid = {
            "WLR_RENDERER": "gles2", "WLR_RENDERER_ALLOW_SOFTWARE": "0",
            "MESA_LOADER_DRIVER_OVERRIDE": "grate",
            "LD_LIBRARY_PATH": "/usr/local/lib/sl101-libdrm-import-lists-" + "a"*16
                               + ":" + module.GRATE_PREFIX_106,
            "LIBGL_DRIVERS_PATH": module.GRATE_PREFIX_106,
            "GBM_BACKENDS_PATH": module.GRATE_PREFIX_106 + "/gbm",
            "LD_PRELOAD": "/usr/local/lib/gr3d_serialize.so",
        }
        pinned = module.validate_compositor_env(valid)
        self.assertEqual(pinned["LD_LIBRARY_PATH"], valid["LD_LIBRARY_PATH"])
        from unittest.mock import patch
        with patch.dict(module.os.environ, {}, clear=True):
            env = module.gpu_environment("/run/user/1000", "wayland-0", pinned)
        self.assertEqual(env["LD_LIBRARY_PATH"], valid["LD_LIBRARY_PATH"])
        self.assertEqual(env["LIBGL_DRIVERS_PATH"], valid["LIBGL_DRIVERS_PATH"])
        self.assertEqual(env["LD_PRELOAD"], "/usr/local/lib/gr3d_serialize.so")
        for key, val in (("WLR_RENDERER", "pixman"),
                         ("WLR_RENDERER_ALLOW_SOFTWARE", "1"),
                         ("MESA_LOADER_DRIVER_OVERRIDE", "swrast"),
                         ("LIBGL_DRIVERS_PATH", "/usr/lib/dri"),
                         ("LD_PRELOAD", "/tmp/random.so"),
                         ("GBM_BACKENDS_PATH", "/tmp/gbm")):
            with self.subTest(key=key, val=val):
                with self.assertRaises(module.GateError):
                    module.validate_compositor_env({**valid, key: val})
        for key in module.GRAPHICS_ENV_KEYS:
            with self.subTest(missing=key), self.assertRaises(module.GateError):
                module.validate_compositor_env({k: v for k, v in valid.items() if k != key})
        with self.assertRaises(module.GateError):
            module.validate_compositor_env({**valid, "GALLIUM_DRIVER": "softpipe"})

    def test_proc_environment_uses_actual_nul_separator(self):
        raw = b"WLR_RENDERER=gles2\x00MESA_LOADER_DRIVER_OVERRIDE=grate\x00"
        raw += b"LD_LIBRARY_PATH=/opt/alpha=beta\x00"
        data = module.parse_proc_environment(raw)
        self.assertEqual(data["WLR_RENDERER"], "gles2")
        self.assertEqual(data["MESA_LOADER_DRIVER_OVERRIDE"], "grate")
        self.assertEqual(data["LD_LIBRARY_PATH"], "/opt/alpha=beta")
        self.assertEqual(len(data), 3)
        for value in ("bad\\npath", "bad\\rpath", "bad\\x00path"):
            valid = {"WLR_RENDERER": "gles2",
                     "WLR_RENDERER_ALLOW_SOFTWARE": "0",
                     "MESA_LOADER_DRIVER_OVERRIDE": "grate",
                     "LD_LIBRARY_PATH": value,
                     "LIBGL_DRIVERS_PATH": module.GRATE_PREFIX_106,
                     "GBM_BACKENDS_PATH": module.GRATE_PREFIX_106 + "/gbm",
                     "LD_PRELOAD": "/usr/local/lib/gr3d_serialize.so"}
            # Invalid embedded controls fail before any graphics launch.
            with self.assertRaises(module.GateError):
                module.validate_compositor_env(valid)

    def test_pinned_mesa_sha_gate(self):
        from unittest.mock import patch
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            filenames = ("libgallium-25.0.7.so", "libEGL.so.1.0.0",
                         "libGLESv2.so.2.0.0")
            digest = {}
            for name in filenames:
                data = ("test-" + name).encode()
                (Path(tmp) / name).write_bytes(data)
                digest[name] = hashlib.sha256(data).hexdigest()
            with patch.object(module, "GRATE_PREFIX_106", tmp), patch.object(
                    module, "GRATE_ELF_SHA256", digest):
                module.verify_grate_libraries(tmp)
                (Path(tmp) / filenames[0]).write_bytes(b"corrupted")
                with self.assertRaises(module.GateError):
                    module.verify_grate_libraries(tmp)

    def test_strict_gpu_libgallium_maps(self):
        from unittest.mock import patch
        prefix = module.GRATE_PREFIX_106
        maps = "\\n".join(prefix + "/" + name for name in module.GRATE_ELF_SHA256)
        with patch.object(module.Path, "read_text", return_value=maps):
            self.assertEqual(module.gpu_maps(10, prefix), (True, False))
        with patch.object(module.Path, "read_text", return_value=maps + "\\n/lib/swrast_dri.so"):
            self.assertEqual(module.gpu_maps(10, prefix), (True, True))
        with patch.object(module.Path, "read_text", return_value="/lib/libgallium-25.0.7.so"):
            self.assertEqual(module.gpu_maps(10, prefix), (False, False))

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
        self.assertEqual(out["command_argv"][6], "location=/tmp/a b ' ; .mp4")
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
