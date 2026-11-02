"""Host-only proof for Grate sampler/mip patch 0018 (no GPU pixel claims)."""
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/mesa-25.0.7/0018-grate-sampler-mipmap-mirror.patch"
SNAPSHOT = ROOT / "work/sl101-grate-mipmap-mirror-0018/after/src/gallium/drivers/grate"


def mip_offsets(width, height, bpp, last):
    """Independent CPU reference, from grate-driver/grate ce8c4d2 alloc_mipmap."""
    offset = 0
    result = []
    for level in range(last + 1):
        w = max(width >> level, 1)
        h = max(height >> level, 1)
        pitch = ((w * bpp + 15) // 16) * 16
        result.append((offset, pitch, w, h))
        offset += pitch * h
    return result, offset


def mirrored_repeat(u):
    """Independent normalized coordinate oracle: ...,1,0,1,0,..."""
    f = u % 2.0
    return f if f <= 1.0 else 2.0 - f


def levels_for_lod(lod, last, between):
    """Independent CPU mip-level oracle; no claim of Tegra20 pixel evidence."""
    x = max(0.0, min(lod, float(last)))
    if between == "NONE":
        return 0, 0, 0.0
    if between == "NEAREST":
        i = min(int(math.floor(x + 0.5)), last)
        return i, i, 0.0
    i = int(math.floor(x))
    return i, min(i + 1, last), x - i


class TextureMipMirrorHostTests(unittest.TestCase):
    def test_patch_has_only_scoped_sources(self):
        patch = PATCH.read_text()
        paths = [line.split(" b/", 1)[1] for line in patch.splitlines()
                 if line.startswith("diff --git ")]
        self.assertEqual(set(paths), {
            f"src/gallium/drivers/grate/{p}" for p in (
                "grate_texture.h", "grate_resource.h", "grate_resource.c",
                "grate_state.h", "grate_state.c", "grate_draw.c")
        })
        self.assertNotIn("TGSI_TEXTURE_CUBE", patch)
        self.assertNotIn("textureCube", patch)

    def test_driver_wiring_and_negative_guards(self):
        patch = PATCH.read_text()
        for text in (
            "PIPE_TEX_WRAP_MIRROR_REPEAT",
            "PIPE_TEX_MIPFILTER_LINEAR",
            "PIPE_TEX_MIPFILTER_NEAREST",
            "grate_texture_desc1_pack_extended",
            "grate_texture_desc2_pack_extended",
            "level_offset[level]",
            "level_pitch[level]",
            "grate_sampler_bindings_supported",
            "template->last_level > max_lod",
            "!grate_texture_is_pow2(template->width0)",
            "view->u.tex.last_level != required",
            "template->u.tex.first_level != 0",
            "template->u.tex.first_layer != 0",
            "grate_texture_is_pow2(width)",
        ):
            self.assertIn(text, patch)

    def test_mipmap_memory_layout_oracle(self):
        levels, size = mip_offsets(8, 4, 4, 3)
        self.assertEqual(levels, [
            (0, 32, 8, 4), (128, 16, 4, 2),
            (160, 16, 2, 1), (176, 16, 1, 1)])
        self.assertEqual(size, 192)
        self.assertEqual(mip_offsets(1, 1, 4, 0), ([(0, 16, 1, 1)], 16))
        self.assertEqual(mip_offsets(2, 2, 1, 1), (
            [(0, 16, 2, 2), (32, 16, 1, 1)], 48))

    def test_mirror_negative_and_positive_coordinates(self):
        for u, expected in (
            (-2.25, 0.25), (-1.25, 0.75), (-0.25, 0.25),
            (0, 0), (0.25, 0.25), (1, 1), (1.25, 0.75),
            (1.75, 0.25), (2.25, 0.25), (3.25, 0.75),
        ):
            self.assertAlmostEqual(mirrored_repeat(u), expected)

    def test_six_minification_modes_reference(self):
        for img_filter, between in (
            ("NEAREST", "NONE"), ("LINEAR", "NONE"),
            ("NEAREST", "NEAREST"), ("LINEAR", "NEAREST"),
            ("NEAREST", "LINEAR"), ("LINEAR", "LINEAR"),
        ):
            self.assertIn(img_filter, ("NEAREST", "LINEAR"))
            low, high, weight = levels_for_lod(2.25, 4, between)
            expected = ((0, 0, 0.0) if between == "NONE"
                        else (2, 2, 0.0) if between == "NEAREST"
                        else (2, 3, 0.25))
            self.assertEqual((low, high, weight), expected)
        self.assertEqual(levels_for_lod(50, 3, "LINEAR"), (3, 3, 0.0))
        self.assertEqual(levels_for_lod(-1, 3, "NEAREST"), (0, 0, 0.0))

    @unittest.skipUnless(shutil.which("cc") and SNAPSHOT.is_dir(),
                         "Native header compilation requires isolated Mesa snapshot")
    def test_actual_descriptor_c_packers(self):
        source = r"""
#include <stdint.h>
#include "grate_texture.h"
int main(void) {
    uint32_t word = 0;
    if (!grate_texture_desc1_pack_extended(0, 1, 1, 0, 0, 1, 1, 1, &word))
        return 1;
    if (word != 0x3800000cu) return 2;
    if (!grate_texture_desc2_pack_extended(256, 128, 8, 1, &word))
        return 3;
    if (word != 0x87008000u) return 4;
    if (grate_texture_desc2_pack_extended(3, 4, 1, 1, &word)) return 5;
    if (grate_texture_desc2_pack_extended(8, 4, 4, 1, &word)) return 6;
    if (grate_texture_desc2_pack_extended(8, 4, 1, 0, &word)) return 7;
    if (!grate_texture_desc2_pack(3, 4, &word)) return 8;
    if (!(word & 0x80u) || !(word & 0x40u)) return 9;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            c = Path(tmp) / "probe.c"
            exe = Path(tmp) / "probe"
            c.write_text(source)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(SNAPSHOT), str(c), "-o", str(exe)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
