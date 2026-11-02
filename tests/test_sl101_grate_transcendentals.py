"""Structural and applyability regression checks for SL101 grate FP SFU patch."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/mesa-25.0.7/0006-grate-fp-transcendentals.patch"
BASE = ROOT / "work/sl101-cog-wpe-20261003/glibc-build/accepted-grate/fp/tgsi.c"


class GrateTranscendentalPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch_text = PATCH.read_text(encoding="utf-8")

    def test_direct_and_twostage_dispatch(self):
        for fragment in (
            "case TGSI_OPCODE_LG2:",
            "FP_SFU_OP_LG2",
            "case TGSI_OPCODE_SQRT:",
            "FP_SFU_OP_SQRT",
            "case TGSI_OPCODE_EX2:",
            "FP_SFU_OP_PREEX2, FP_SFU_OP_EX2",
            "case TGSI_OPCODE_SIN:",
            "FP_SFU_OP_PRESIN, FP_SFU_OP_SIN",
            "case TGSI_OPCODE_COS:",
            "FP_SFU_OP_PRECOS, FP_SFU_OP_COS",
        ):
            self.assertIn(fragment, self.patch_text)

    def test_source_and_schedule_invariants(self):
        for fragment in (
            "fp_sfu_source_gpr(",
            "fp_emit_alu(fp, lowering, &mov, true)",
            "FP_MFU_MUL_SRC_SFU_RESULT",
            "FP_MFU_MUL_DST_ROW_REG_0",
            "list_length(&fp->fp_instructions) + steps > 63",
            "fp_dst_component(fp, dst, c, saturate, &d)",
            "last_exec > fp->info.pseq_to_dw_exec_nb",
        ):
            self.assertIn(fragment, self.patch_text)

    @unittest.skipUnless(BASE.is_file(), "generated production source unavailable")
    def test_patch_applies_to_baseline(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "src/gallium/drivers/grate/fp/tgsi.c"
            target.parent.mkdir(parents=True)
            target.write_bytes(BASE.read_bytes())
            p = subprocess.run(
                ["patch", "--batch", "--dry-run", "-p1", "-i", str(PATCH)],
                cwd=scratch, capture_output=True, text=True, check=False
            )
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
