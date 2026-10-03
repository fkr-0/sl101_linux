"""Host checks for the independent compositor-semantics oracle."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = spec_from_file_location("regression", HERE.parent / "scripts/sl101-compositor-pixel-qualification.py")
assert SPEC and SPEC.loader
reg = module_from_spec(SPEC)
SPEC.loader.exec_module(reg)


class OracleTests(unittest.TestCase):
    def test_premultiplied_source_over_is_not_straight_alpha(self):
        # 50% red over the parent background.
        a = 128
        src = (reg.premul(220, a), reg.premul(41, a), reg.premul(137, a))
        out = reg.source_over(src, a, (17, 53, 91))
        self.assertEqual(out, (118, 47, 114))
        self.assertNotEqual(out[0], (220 * a + 17 * (255 - a) + 127) // 255)

    def test_xrgb_patch_and_padding_geometry_are_distinct(self):
        self.assertEqual(reg.XRGB_W * 4, 692)
        self.assertEqual(reg.XRGB_W * 4 + reg.XRGB_PAD, 744)
        self.assertEqual(reg.xrgb_rgb(reg.XRGB_PATCH_X, reg.XRGB_PATCH_Y),
                         (201, 33, 149))
        self.assertNotEqual(reg.xrgb_rgb(0, 0), (201, 33, 149))

    def test_overlap_composes_argb_above_xrgb(self):
        gx, gy = reg.ARGB_X, reg.ARGB_Y
        local_x = gx - reg.XRGB_X
        local_y = gy - reg.XRGB_Y
        below = reg.xrgb_rgb(local_x, local_y)
        sr, sg, sb, a = reg.argb_premul(0, 0)
        self.assertEqual(
            reg.expected_rgb(gx, gy, 1280, 720),
            reg.source_over((sr, sg, sb), a, below),
        )

    def test_parent_damage_patch_is_final_phase_content(self):
        x, y = 1280 - 140, 720 - 95
        self.assertEqual(reg.parent_rgb(x, y, 1280, 720), (7, 211, 79))
        self.assertEqual(reg.parent_rgb(0, 0, 1280, 720), (17, 53, 91))

    def test_exact_oracle_passes_and_swizzle_fails(self):
        width, height = 480, 320
        reference = reg.oracle(width, height)
        exact = reg.compare(reference, reference, width, height)
        self.assertTrue(exact["pass"])
        swizzled = bytearray(reference)
        red = bytes(swizzled[2::4])
        blue = bytes(swizzled[0::4])
        swizzled[0::4] = red
        swizzled[2::4] = blue
        result = reg.compare(bytes(swizzled), reference, width, height)
        self.assertFalse(result["pass"])
        self.assertGreater(result["regions"]["xrgb_all"]["wrong_fraction"], 0.5)

    def test_one_row_shift_is_detected_in_padded_texture_region(self):
        width, height = 480, 320
        reference = reg.oracle(width, height)
        actual = bytearray(reference)
        # Shift only the visible XRGB rectangle by one row to emulate pitch/row
        # addressing breakage while preserving the rest of the compositor frame.
        row_bytes = width * 4
        for y in range(reg.XRGB_Y, reg.XRGB_Y + reg.XRGB_H - 1):
            dst = y * row_bytes + reg.XRGB_X * 4
            src = (y + 1) * row_bytes + reg.XRGB_X * 4
            actual[dst:dst + reg.XRGB_W * 4] = reference[
                src:src + reg.XRGB_W * 4
            ]
        result = reg.compare(bytes(actual), reference, width, height)
        self.assertFalse(result["pass"])
        self.assertGreater(result["regions"]["xrgb_all"]["wrong_fraction"], 0.5)

    def test_small_damaged_region_cannot_hide_in_global_average(self):
        width, height = 480, 320
        reference = reg.oracle(width, height)
        actual = bytearray(reference)
        x = reg.XRGB_X + reg.XRGB_PATCH_X
        y = reg.XRGB_Y + reg.XRGB_PATCH_Y
        for offset in range(6):
            actual[(y * width + x + offset) * 4] = 0
        result = reg.compare(bytes(actual), reference, width, height)
        self.assertLess(result["wrong_fraction"], 0.001)
        self.assertFalse(result["regions"]["xrgb_patch"]["pass"])
        self.assertFalse(result["pass"])


if __name__ == "__main__":
    unittest.main()
