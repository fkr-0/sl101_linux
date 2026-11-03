"""Lane 03: static source checks for DP2 lowering; not real GPU execution."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DP2 = ROOT / "patches/mesa-25.0.7/0037-grate-fp-dp2.patch"
DOT = ROOT / "patches/mesa-25.0.7/0012-grate-fp-frc-dp3-dp4.patch"


class FPDP2Patch(unittest.TestCase):
    def test_dp2_reuses_scalar_dot_lowerer(self):
        dp2, dot = DP2.read_text(), DOT.read_text()
        self.assertRegex(dp2, r"fp_emit_dp2\([^;]*?\+\{\n\+   return fp_emit_dot\(fp, lowering, tgsi_inst, 2\);")
        self.assertIn("+            case TGSI_OPCODE_DP2:", dp2)
        self.assertIn("+               fp_emit_dp2(fp, &lowering, inst);", dp2)
        for dimension in (3, 4):
            self.assertIn(f"return fp_emit_dot(fp, lowering, tgsi_inst, {dimension});", dot)
        self.assertIn("op.Instruction.Opcode = c == 0 ? TGSI_OPCODE_MUL : TGSI_OPCODE_MAD;", dot)
        self.assertIn("fp_dot_scratch", dot)
        self.assertIn("source_mask", dot)
        self.assertIn("direct_final = false;", dot)

    def test_no_cap_spoof(self):
        text = DP2.read_text()
        self.assertEqual(text.count("--- a/"), 1)
        self.assertNotRegex(text, r"PIPE_CAP|GL_MAX|MAX_FRAGMENT_UNIFORM")


if __name__ == "__main__":
    unittest.main()
