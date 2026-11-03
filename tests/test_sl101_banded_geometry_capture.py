"""Regression from read-only Nura .106 GRATE_DEBUG=format capture (2026-11-03)."""
import pathlib
import struct
import unittest

from test_sl101_banded_geometry import fetch

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "work/scanout-followups-20261103/coordinator-captures/sl101-kms-fmt.log"
CAPTURE_SHA256 = "5559b48e43f7f93b3dfa55229d4cd6e3391c9218f12f508b241654ddda98bdb1"

# Literal, attributed fixture from first two attrib_emit lines (62, 63);
# tested independent of capture file presence. Debug bytes already begin
# at buffer_offset + elem_offset: do NOT apply slot1's +12 twice.
POS = bytes.fromhex(
    "0000804400000000000000ff0000000000000000"
    "0000804400008043000000ff0000000000008043"
    "0000a04400000000"
)
UV = bytes.fromhex(
    "00000000000000000000804400008043000000ff"
    "00000000000080430000a04400000000000000ff"
    "0000804300000000"
)


class CapturedGeometryTests(unittest.TestCase):
    def test_capture_fixture_decodes_at_correct_dump_start(self):
        self.assertEqual((len(POS), len(UV)), (48, 48))
        self.assertEqual(fetch(POS, 20, 0, [0, 1, 2]),
                         [(1024., 0.), (1024., 256.), (1280., 0.)])
        self.assertEqual(fetch(UV, 20, 0, [0, 1, 2]),
                         [(0., 0.), (0., 256.), (256., 0.)])
        self.assertNotEqual(fetch(UV, 20, 12, [0]), [(0., 0.)])
        with self.assertRaises(struct.error):
            fetch(POS, 20, 0, [3])

    def test_original_capture_matches_attributed_fixture_if_present(self):
        if not CAPTURE.exists():
            self.skipTest("read-only source capture not present")
        import hashlib
        import re
        logbytes = CAPTURE.read_bytes()
        self.assertEqual(hashlib.sha256(logbytes).hexdigest(), CAPTURE_SHA256)
        log = logbytes.decode("utf-8", errors="replace")
        for slot, expected, offset in ((0, POS, 0), (1, UV, 12)):
            match = re.search(
                rf"^grate: attrib_emit slot={slot} .*?buffer_offset={offset} .*?bytes=([0-9a-f,]+)",
                log, re.MULTILINE)
            self.assertIsNotNone(match)
            data = bytes(int(x, 16) for x in match.group(1).split(",")[:48])
            self.assertEqual(data, expected)
        self.assertIn("grate: vp constants words=16", log)
        self.assertIn("grate: vp constants words=4", log)


if __name__ == "__main__":
    unittest.main()
