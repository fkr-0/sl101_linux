"""CPU-only unit tests of the real ARMHF DT_NEEDED audit logic."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "packaging/audit-armhf-needed.py"
SPEC = importlib.util.spec_from_file_location("needed_audit", SRC)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

HEADER = ("ELF Header:\n  Machine:                           ARM\n"
          "  Flags:                             0x5000400, Version5 EABI, hard-float ABI\n")
ARM_ATTR = "Attribute Section: aeabi\n  Tag_CPU_arch: v7\n  Tag_FP_arch: VFPv3-D16\n"
SIMD_ATTR = ARM_ATTR + "  Tag_Advanced_SIMD_arch: NEONv1\n"
DEP = ("Dynamic section:\n 0x00000001 (NEEDED) "
       "Shared library: [libwebp.so.7]\n")
NO_DEP = "Dynamic section:\n 0x0000000e (SONAME) Library soname: [libtest.so.1]\n"


class NeededAuditTests(unittest.TestCase):
    def make_elf(self, folder: Path, name: str) -> Path:
        path = folder / name
        path.write_bytes(b"\x7fELF" + b"\0" * 24)
        return path

    def test_parse_missing_neon_attribute(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_elf(Path(td), "app")
            with patch.object(audit, "read_elf", side_effect=[HEADER, ARM_ATTR, DEP]):
                result = audit.inspect_elf(path)
            self.assertEqual(result["needed"], ["libwebp.so.7"])
            self.assertIsNone(result["simd"])
            self.assertFalse(result["problems"])

    def test_neon_library_is_unsafe(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_elf(Path(td), "libwebp.so.7")
            with patch.object(audit, "read_elf", side_effect=[HEADER, SIMD_ATTR, NO_DEP]):
                result = audit.inspect_elf(path)
            self.assertTrue(any("NEONv1" in p for p in result["problems"]))

    def test_missing_dependency_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_elf(Path(td), "app")
            with patch.object(audit, "read_elf", side_effect=[HEADER, ARM_ATTR, DEP]):
                report = audit.closure(path, [Path(td)])
            self.assertFalse(report["pass"])
            self.assertEqual(report["missing"][0]["soname"], "libwebp.so.7")

    def test_transitive_unsafe_dependency_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_elf(Path(td), "app")
            lib = self.make_elf(Path(td), "libwebp.so.7")
            def responses(p, flag):
                attr = SIMD_ATTR if p == lib else ARM_ATTR
                return {"-h": HEADER, "-A": attr,
                        "-d": NO_DEP if p == lib else DEP}[flag]
            with patch.object(audit, "read_elf", side_effect=responses):
                report = audit.closure(path, [Path(td)])
            self.assertFalse(report["pass"])
            self.assertEqual(report["elf_count"], 2)
            self.assertEqual(len(report["unsafe"]), 1)
            self.assertEqual(report["unsafe"][0]["path"], str(lib))

    def test_non_arm_and_soft_float_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_elf(Path(td), "bad")
            bad = HEADER.replace("ARM", "X86-64").replace("hard-float ABI", "soft-float ABI")
            with patch.object(audit, "read_elf", side_effect=[bad, ARM_ATTR, NO_DEP]):
                inspected = audit.inspect_elf(path)
            self.assertIn("not ARM ELF", inspected["problems"])
            self.assertIn("not ARM EABI hard-float", inspected["problems"])


if __name__ == "__main__":
    unittest.main()
