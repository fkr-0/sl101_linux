"""Deterministic host vertex decode and compiled GLES2 pixel tests."""
import os
import pathlib
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DRIVER = ROOT / "build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate"


def fetch(data, stride, offset, order, basevertex=0):
    """The caller must supply real VBO-start offset and actual draw indices."""
    return [struct.unpack_from("<2f", data, (i + basevertex) * stride + offset)
            for i in order]


class GeometryTests(unittest.TestCase):
    def test_strides_offsets_packed_and_index_modes(self):
        positions = [(0., 0.), (1., 0.), (1., 1.), (0., 1.)]
        for stride in (8, 16, 20, 32):
            for offset in (0, 12):
                if offset + 8 > stride:
                    continue
                data = bytearray(4 * stride)
                for i, position in enumerate(positions):
                    struct.pack_into("<2f", data, i * stride + offset, *position)
                    if offset:
                        struct.pack_into("<I", data, i * stride, 0xff000000)
                self.assertEqual(fetch(data, stride, offset, range(4)), positions)
                self.assertEqual(fetch(data, stride, offset, [0, 1, 2, 0, 2, 3]),
                                 [positions[i] for i in (0, 1, 2, 0, 2, 3)])
                if offset:
                    self.assertNotEqual(fetch(data, stride, 0, range(4)), positions)

    def test_basevertex_and_dump_start(self):
        stride, offset = 20, 12
        data = bytearray(stride * 6)
        for i in range(6):
            struct.pack_into("<2f", data, i * stride + offset, float(i), float(i + 10))
        self.assertEqual(fetch(data, stride, offset, [0, 2], basevertex=2),
                         [(2., 12.), (4., 14.)])
        self.assertNotEqual(fetch(data, stride, 0, [0]),
                            fetch(data[offset:], stride, 0, [0]))

    def test_grate_register_semantics(self):
        # Check the real pinned driver source rather than a copied mode formula.
        source = (DRIVER / "grate_state.c").read_text()
        registers = (DRIVER / "tgr_3d.xml.h").read_text()
        match = re.search(r"#define TGR3D_ATTRIB_MODE_STRIDE__SHIFT\s+(\d+)", registers)
        self.assertIsNotNone(match)
        self.assertEqual(0x0000142d >> int(match.group(1)), 20)
        self.assertIn("attrib |= TGR3D_VAL(ATTRIB_MODE, STRIDE, e->stride)", source)
        self.assertIn("vb->buffer_offset + e->offset", source)
        self.assertIn("drm_tegra_bo_map(r->bo, &map)", source)

    @unittest.skipUnless(shutil.which("cc") and shutil.which("pkg-config"), "C toolchain")
    def test_compiled_softpipe_oracle(self):
        if subprocess.run(["pkg-config", "--exists", "egl", "glesv2"]).returncode:
            self.skipTest("EGL/GLES2 development packages not installed")
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "egl", "glesv2"], text=True
        ).split()
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "geometry"
            subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror",
                            str(ROOT / "fbl/sl101-banded-geometry-repro.c"),
                            "-o", str(exe), *flags, "-lm"], check=True)
            env = dict(os.environ, EGL_PLATFORM="surfaceless", LIBGL_ALWAYS_SOFTWARE="1")
            hashes = set()
            for stride in (8, 16, 20, 32):
                for offset in (0, 12):
                    if offset + 8 > stride:
                        continue
                    for mode in ("indexed", "arrays"):
                        proc = subprocess.run([str(exe), str(stride), str(offset), mode],
                                              capture_output=True, text=True, env=env)
                        if proc.returncode == 77:
                            self.skipTest("No host surfaceless EGL")
                        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                        hashes.add(proc.stdout.rsplit("fnv=", 1)[-1].strip())
            self.assertEqual(len(hashes), 1, "same pixels for all equivalent layouts")


if __name__ == "__main__":
    unittest.main()
