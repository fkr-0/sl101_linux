"""Lane 03: patch contracts and compiled host lowering regression; no GPU pixels."""
from pathlib import Path
import re
import subprocess
import sys
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

    def test_compiled_native_dp2_regression(self):
        # Optional unit test for developer hosts; explicit qualification is NEVER optional.
        runner = ROOT / "scripts/sl101-fbl03-native-qualify.py"
        build = ROOT / "build/mesa-grate-clean/mesa-25.0.7/builddir/build.ninja"
        self.assertTrue(runner.is_file(), "tracked native qualification runner missing")
        if not build.is_file():
            self.skipTest("configured Mesa build absent; run explicit native qualification")
        result = subprocess.run([sys.executable, str(runner)], cwd=ROOT,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: 14 grate FRC/DP lowering structural tests", result.stdout)

    def test_native_qualification_fails_missing_build(self):
        runner = ROOT / "scripts/sl101-fbl03-native-qualify.py"
        result = subprocess.run([sys.executable, str(runner), "--mesa-build",
                                 str(ROOT / "tests/fixtures/sl101-fbl03-native/no-build")],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing configured Mesa build.ninja", result.stderr)

    def test_no_cap_spoof(self):
        text = DP2.read_text()
        self.assertEqual(text.count("--- a/"), 1)
        self.assertNotRegex(text, r"PIPE_CAP|GL_MAX|MAX_FRAGMENT_UNIFORM")


if __name__ == "__main__":
    unittest.main()
