"""Host-only lane04 stencil register and fail-closed contract checks."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
XML = ROOT / "build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate/tgr_3d.xml.h"
PATCH = ROOT / "patches/mesa-25.0.7/0032-grate-stencil-state-readonly.patch"


class StencilContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not XML.is_file():
            raise unittest.SkipTest("local generated Mesa header unavailable")
        cls.xml = XML.read_text()
        cls.patch = PATCH.read_text()

    def macro(self, name):
        match = re.search(r"^#define\s+" + re.escape(name) + r"\s+(0x[0-9a-fA-F]+|[0-9]+)", self.xml, re.M)
        self.assertIsNotNone(match, name)
        return int(match.group(1), 0)

    def test_stencil_ops(self):
        for name, value in {"ZERO": 0, "KEEP": 1, "REPLACE": 2, "INCR": 3,
                            "DECR": 4, "INVERT": 5, "INCR_WRAP": 6,
                            "DECR_WRAP": 7}.items():
            self.assertEqual(self.macro("TGR3D_STENCIL_OP_" + name), value)

    def test_register_fields_and_enable(self):
        self.assertEqual(self.macro("TGR3D_STENCIL_PARAMS_STENCIL_TEST"), 0x20)
        self.assertEqual(self.macro("TGR3D_STENCIL_PARAMS_STENCIL_WRITE_EARLY"), 0x40)
        self.assertEqual(self.macro("TGR3D_STENCIL_FRONT2_REF__MASK"), 0x03fe0000)
        self.assertEqual(self.macro("TGR3D_STENCIL_FRONT2_REF__SHIFT"), 17)
        for field, mask in [("OP_FAIL", 7), ("OP_ZFAIL", 0x38), ("OP_ZPASS", 0x1c0)]:
            self.assertEqual(self.macro("TGR3D_STENCIL_FRONT2_" + field + "__MASK"), mask)

    def test_current_patch_fail_closed(self):
        self.assertIn("grate_stencil_draw_supported", self.patch)
        self.assertIn("grate_stencil_keep_only", self.patch)
        self.assertIn("stencil_unsupported", self.patch)
        self.assertIn("PIPE_STENCIL_OP_KEEP", self.patch)
        self.assertNotIn("TGR3D_STENCIL_OP_REPLACE)", self.patch)


if __name__ == "__main__":
    unittest.main()
