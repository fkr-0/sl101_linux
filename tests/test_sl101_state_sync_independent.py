"""Independent CPU reference oracles for SL101 Grate state/sync review.

No hardware, Mesa-tree mutation or GLES2 conformance is implied.
Compare future driver tests against these independent expected semantics.
"""
from __future__ import annotations

from itertools import product
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches/mesa-25.0.7"
S = (0.8, 0.2, 0.5, 0.25)
D = (0.1, 0.6, 0.3, 0.75)
C = (0.35, 0.65, 0.15, 0.4)


def clamp(v):
    return max(0.0, min(1.0, v))


def blend_factor(name, channel, src, dst, constant):
    def component(color):
        return color[channel]
    factors = {
        "ZERO": 0.0, "ONE": 1.0,
        "SRC_COLOR": component(src), "ONE_MINUS_SRC_COLOR": 1 - component(src),
        "DST_COLOR": component(dst), "ONE_MINUS_DST_COLOR": 1 - component(dst),
        "SRC_ALPHA": src[3], "ONE_MINUS_SRC_ALPHA": 1 - src[3],
        "DST_ALPHA": dst[3], "ONE_MINUS_DST_ALPHA": 1 - dst[3],
        "CONSTANT_COLOR": component(constant),
        "ONE_MINUS_CONSTANT_COLOR": 1 - component(constant),
        "CONSTANT_ALPHA": constant[3],
        "ONE_MINUS_CONSTANT_ALPHA": 1 - constant[3],
        # ES2 SRC_ALPHA_SATURATE has alpha factor 1, RGB min(src.a,1-dst.a).
        "SRC_ALPHA_SATURATE": 1.0 if channel == 3 else min(src[3], 1 - dst[3]),
    }
    return factors[name]


def reference_blend(src, dst, rgb_src, rgb_dst, alpha_src, alpha_dst,
                    rgb_eq="ADD", alpha_eq="ADD", color_mask=0xF,
                    constant=C):
    out = []
    for i in range(4):
        sf = blend_factor(rgb_src if i < 3 else alpha_src, i, src, dst, constant)
        df = blend_factor(rgb_dst if i < 3 else alpha_dst, i, src, dst, constant)
        a, b = src[i] * sf, dst[i] * df
        equation = rgb_eq if i < 3 else alpha_eq
        result = {"ADD": a + b, "SUBTRACT": a - b,
                  "REVERSE_SUBTRACT": b - a}[equation]
        out.append(clamp(result) if color_mask & (1 << i) else dst[i])
    return tuple(out)


STENCIL_COMPARE = {
    "NEVER": lambda r, s: False,
    "LESS": lambda r, s: r < s,
    "LEQUAL": lambda r, s: r <= s,
    "GREATER": lambda r, s: r > s,
    "GEQUAL": lambda r, s: r >= s,
    "EQUAL": lambda r, s: r == s,
    "NOTEQUAL": lambda r, s: r != s,
    "ALWAYS": lambda r, s: True,
}


def reference_stencil(old, reference, read_mask, write_mask, compare,
                      stencil_fail, depth_fail, depth_pass, depth_ok):
    # Reference is the left-hand operand (ref & read_mask).
    passed = STENCIL_COMPARE[compare](reference & read_mask, old & read_mask)
    op = stencil_fail if not passed else depth_pass if depth_ok else depth_fail
    candidate = {
        "KEEP": old, "ZERO": 0, "REPLACE": reference,
        "INCR": min(255, old + 1), "DECR": max(0, old - 1),
        "INCR_WRAP": (old + 1) & 255, "DECR_WRAP": (old - 1) & 255,
        "INVERT": old ^ 255,
    }[op] & 255
    updated = (old & (~write_mask & 255)) | (candidate & write_mask & 255)
    return passed, updated


def reference_selective_clear(old_depth, old_stencil, flags, new_depth, new_stencil):
    # Semantic oracle for a hypothetical combined attachment (not supported by 0019).
    return (new_depth if flags & 1 else old_depth,
            new_stencil if flags & 2 else old_stencil)


def preflight_draw(first, count, index_size=0, indices=None,
                   mode="LINE_LOOP", first_bits=24, offset_bits=20):
    # Abstract reject-before-submit oracle; not a model of register execution.
    if count == 0:
        return True
    if first < 0 or count < 0 or first + count - 1 > (1 << first_bits) - 1:
        return False
    if index_size:
        if indices is None or first + count > len(indices):
            return False
        if (first * index_size) > (1 << offset_bits) - 1:
            return False
        if any(x < 0 or x > 65535 for x in indices[first:first + count]):
            return False
    elif mode in ("LINE_LOOP", "TRIANGLE_FAN") and count > 2047:
        if first + count - 1 > 65535:
            return False
    return True


class ReferenceStateMatrix(unittest.TestCase):
    def test_0010_blend_variants_and_alpha_separate(self):
        self.assertEqual(tuple(round(x, 6) for x in reference_blend(
            S, D, "SRC_ALPHA", "ONE_MINUS_SRC_ALPHA",
            "SRC_ALPHA", "ONE_MINUS_SRC_ALPHA")),
            (0.275, 0.5, 0.35, 0.625))
        premul = reference_blend(S, D, "ONE", "ONE_MINUS_SRC_ALPHA",
                                 "ONE", "ONE_MINUS_SRC_ALPHA")
        self.assertEqual(tuple(round(x, 6) for x in premul),
                         (0.875, 0.65, 0.725, 0.8125))
        self.assertEqual(tuple(round(x, 6) for x in reference_blend(
            S, D, "ONE", "ONE", "ONE", "ONE")),
            (0.9, 0.8, 0.8, 1.0))
        # Premultiplied RGB inputs .8*.25, .2*.25, .5*.25
        psrc = (0.2, 0.05, 0.125, 0.25)
        self.assertEqual(tuple(round(x, 6) for x in reference_blend(
            psrc, D, "ONE", "ONE_MINUS_SRC_ALPHA", "ONE", "ONE_MINUS_SRC_ALPHA")),
            (0.275, 0.5, 0.35, 0.8125))

    def test_all_core_es2_blend_factor_equation_pairs(self):
        factors = ("ZERO", "ONE", "SRC_COLOR", "ONE_MINUS_SRC_COLOR",
                   "DST_COLOR", "ONE_MINUS_DST_COLOR", "SRC_ALPHA",
                   "ONE_MINUS_SRC_ALPHA", "DST_ALPHA", "ONE_MINUS_DST_ALPHA",
                   "CONSTANT_COLOR", "ONE_MINUS_CONSTANT_COLOR",
                   "CONSTANT_ALPHA", "ONE_MINUS_CONSTANT_ALPHA")
        for sf, df, eq in product(factors, factors,
                                  ("ADD", "SUBTRACT", "REVERSE_SUBTRACT")):
            result = reference_blend(S, D, sf, df, "ONE", "ZERO", eq)
            self.assertTrue(all(0 <= x <= 1 for x in result))
            # Full mask vs RGB-only mask retains destination alpha.
            masked = reference_blend(S, D, sf, df, "ONE", "ZERO", eq,
                                     color_mask=0x7)
            self.assertEqual(masked[3], D[3])
            self.assertEqual(masked[:3], result[:3])

    def test_stencil_full_compare_op_matrix_front_back_independent(self):
        ops = ("KEEP", "ZERO", "REPLACE", "INCR", "DECR", "INCR_WRAP",
               "DECR_WRAP", "INVERT")
        # All GL ES2 compare functions, write masks, outcomes, each face independent.
        for face, ref, old, read_mask, write_mask, cmp, op, depth_ok in product(
            ("FRONT", "BACK"), (0, 17, 255), (0, 17, 255),
            (0x00, 0x55, 0xFF), (0x00, 0x0F, 0xFF),
            STENCIL_COMPARE, ops, (False, True)
        ):
            passed, updated = reference_stencil(
                old, ref, read_mask, write_mask, cmp, op, op, op, depth_ok)
            self.assertEqual(updated & (~write_mask & 255),
                             old & (~write_mask & 255), face)
            self.assertTrue(0 <= updated <= 255, face)
            self.assertEqual(passed, STENCIL_COMPARE[cmp](
                ref & read_mask, old & read_mask), face)

    def test_stencil_distinguish_sfail_zfail_zpass(self):
        for cmp, depth_ok, expected in (
            ("NEVER", True, 0), ("ALWAYS", False, 18), ("ALWAYS", True, 16)
        ):
            _, got = reference_stencil(17, 23, 255, 255, cmp,
                                      "ZERO", "INCR", "DECR", depth_ok)
            self.assertEqual(got, expected)
        self.assertEqual(reference_stencil(255, 123, 255, 255, "ALWAYS",
                                           "KEEP", "KEEP", "INCR_WRAP", True)[1], 0)

    def test_selective_clear_preserves_other_component(self):
        for flags in range(4):
            depth, stencil = reference_selective_clear(0xBEEF, 0x6D, flags,
                                                       0x1234, 0xA5)
            self.assertEqual(depth, 0x1234 if flags & 1 else 0xBEEF)
            self.assertEqual(stencil, 0xA5 if flags & 2 else 0x6D)
        patch = (PATCHES / "0019-grate-selective-depth-stencil-clear.patch").read_text()
        self.assertIn("PIPE_FORMAT_Z16_UNORM:", patch)
        self.assertIn("PIPE_FORMAT_S8_UINT:", patch)
        self.assertIn("unsupported depth/stencil clear format", patch)

    def test_draw_65537_connected_field_and_index_limits(self):
        self.assertTrue(preflight_draw(0, 65536))
        self.assertFalse(preflight_draw(0, 65537))
        self.assertFalse(preflight_draw(1 << 24, 1, mode="TRIANGLES"))
        self.assertFalse(preflight_draw(1 << 20, 1, index_size=1,
                                        indices=[0] * ((1 << 20) + 1)))
        self.assertFalse(preflight_draw(0, 3, index_size=4,
                                        indices=[0, 65536, 1]))
        self.assertTrue(preflight_draw(0, 3, index_size=4,
                                       indices=[2, 100, 65535]))
        self.assertTrue(preflight_draw(0, 0, index_size=4, indices=[]))

    def test_fence_patch_is_interim_not_fault_safe_teardown(self):
        patch = (PATCHES / "0027-grate-fence-error-lifetime.patch").read_text()
        self.assertIn("const unsigned long timeout_ms = 5000;", patch)
        self.assertIn("CPU map denied", patch)
        self.assertIn("BO safety requires kernel fault qualification", patch)
        self.assertNotIn("grate_channel_delete", patch)
        draw_patch = (PATCHES / "0026-grate-draw-restart-multidraw.patch").read_text()
        self.assertIn("primitive restart is unsupported", draw_patch)
        self.assertIn("if (!draw.count)", draw_patch)


if __name__ == "__main__":
    unittest.main()
