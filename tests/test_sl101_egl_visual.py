"""Checks that the visual acceptance oracle rejects distorted pixel data."""
import importlib.util
from pathlib import Path

import unittest

spec = importlib.util.spec_from_file_location(
    "sl101_visual", Path(__file__).parents[1] / "scripts/sl101-egl-visual-regression.py"
)
visual = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visual)


class VisualOracleTests(unittest.TestCase):
    def test_exact_image_and_unused_alpha_pass(self):
        reference = visual.oracle(128, 72)
        actual = bytearray(reference)
        actual[3::4] = bytes(len(actual) // 4)
        result = visual.compare(actual, reference)
        assert result["pass"] and result["wrong_pixels"] == 0


    def test_blank_successful_framebuffer_is_not_a_visual_pass(self):
        reference = visual.oracle(128, 72)
        result = visual.compare(bytes(len(reference)), reference)
        assert not result["pass"] and result["wrong_fraction"] > 0.99


    def test_fixture_readiness_uses_coordinate_channels_not_checker_palette(self):
        reference = visual.oracle(128, 72)
        assert len(set(reference[0::4])) == 3
        assert visual.nonblank(reference)
        assert not visual.nonblank(bytes(len(reference)))


    def test_wrong_row_stride_is_rejected(self):
        width, height = 128, 72
        reference = visual.oracle(width, height)
        # Geometry stays correct, but each source row starts at the wrong texel.
        actual = b"".join(reference[y * width * 4 + 4:(y + 1) * width * 4] +
                          reference[y * width * 4:y * width * 4 + 4]
                          for y in range(height))
        result = visual.compare(actual, reference)
        assert not result["pass"] and result["wrong_fraction"] > 0.05


    def test_channel_swizzle_and_vertical_flip_are_rejected(self):
        reference = visual.oracle(128, 72)
        actual = bytearray(reference)
        actual[0::4], actual[2::4] = actual[2::4], actual[0::4]
        assert not visual.compare(actual, reference)["pass"]
        rows = [reference[y * 128 * 4:(y + 1) * 128 * 4] for y in range(72)]
        assert not visual.compare(b"".join(reversed(rows)), reference)["pass"]


    def test_small_rounding_error_passes_but_widespread_error_fails(self):
        reference = bytes([100, 100, 100, 255]) * 100
        assert visual.compare(bytes([102, 99, 101, 0]) * 100, reference)["pass"]
        assert not visual.compare(bytes([103, 100, 100, 255]) * 100, reference)["pass"]


    def test_incomplete_or_mismatched_capture_fails_closed(self):
        for actual in (b"", b"abc", bytes(8)):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                visual.compare(actual, bytes(4))
