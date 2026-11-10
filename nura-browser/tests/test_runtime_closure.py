"""CPU-only tests for the offline ARMHF DT_NEEDED/ISA release gate."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts/audit-runtime-closure.py"
SPEC = spec_from_file_location("nura_runtime_closure", SOURCE)
AUDIT = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(AUDIT)


class RuntimeClosureTests(TestCase):
    def test_needed_parser(self):
        text = (
            " 0x00000001 (NEEDED) Shared library: [libwebp.so.7]\n"
            " 0x00000001 (NEEDED) Shared library: [libc.so.6]\n"
            " 0x0000000f (RPATH) Library rpath: [$ORIGIN]\n"
        )
        self.assertEqual(AUDIT.parse_needed(text), ["libwebp.so.7", "libc.so.6"])

    def test_simd_attributes(self):
        self.assertTrue(AUDIT.is_neon_attribute("Tag_Advanced_SIMD_arch: NEONv1"))
        self.assertTrue(AUDIT.is_neon_attribute("Tag_Advanced_SIMD_arch: NEON"))
        self.assertFalse(AUDIT.is_neon_attribute(
            "Tag_CPU_arch: v7\nTag_FP_arch: VFPv3-D16\n"
        ))

    def test_neon_with_only_low_d_registers(self):
        self.assertIn("vadd.i8", AUDIT.flagged_disassembly_line(
            "    0120: f2020804     vadd.i8  d0, d2, d4"
        ))
        self.assertIn("vld1.8", AUDIT.flagged_disassembly_line(
            "    0124: f420070f     vld1.8 {d0}, [r0]"
        ))
        self.assertIn("q2", AUDIT.flagged_disassembly_line(
            "    0128: f2000250     vadd.f32 q2, q1, q0"
        ))
        self.assertIsNone(AUDIT.flagged_disassembly_line(
            "    012c: ee300b01     vadd.f64 d0, d0, d1"
        ))
        self.assertIn("vfma.f64", AUDIT.flagged_disassembly_line(
            "   3a470: eea02b01     vfma.f64 d2, d0, d1"
        ))
        self.assertIn("vadd.f32", AUDIT.flagged_disassembly_line(
            "   3a474: f2000d12     vadd.f32 d0, d2, d4"
        ))
        self.assertIsNone(AUDIT.flagged_disassembly_line(
            "   3a478: ee300a81     vadd.f32 s0, s1, s2"
        ))
        self.assertIn("vabal.u8", AUDIT.flagged_disassembly_line(
            "   3a47c: f2800d12     vabal.u8 d0, d2, d4"
        ))

    def test_safe_library_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            lib = root / "usr/lib/arm-linux-gnueabihf"
            lib.mkdir(parents=True)
            target = lib / "libsafe.so.1.0"
            target.write_bytes(b"\x7fELF\x00")
            (lib / "libsafe.so.1").symlink_to("libsafe.so.1.0")
            self.assertEqual(AUDIT.resolve_library(root, "libsafe.so.1"), target)
            self.assertIsNone(AUDIT.resolve_library(root, "../../etc/passwd"))
            self.assertIsNone(AUDIT.resolve_library(root, "/etc/passwd"))
            (lib / "libescape.so.1").symlink_to("/etc/passwd")
            self.assertIsNone(AUDIT.resolve_library(root, "libescape.so.1"))

    def test_missing_transitive_dependency_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = root / "usr/bin/nura"
            app.parent.mkdir(parents=True)
            app.write_bytes(b"\x7fELF\x00")
            def mocked_readelf(*argv):
                if "-hW" in argv:
                    return "Machine: ARM\nFlags: hard-float ABI\n"
                if "-A" in argv:
                    return "Tag_CPU_arch: v7\nTag_FP_arch: VFPv3-D16\n"
                return "(NEEDED) Shared library: [libmissing.so.0]\n"
            with patch.object(AUDIT, "run", side_effect=mocked_readelf):
                result = AUDIT.scan(root, app, full=False, objdump="unused")
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["pass"])
            self.assertEqual(result["missing"][0]["needed"], "libmissing.so.0")

    def test_neon_dependency_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = root / "bin/nura"
            app.parent.mkdir(parents=True)
            app.write_bytes(b"\x7fELF\x00")
            directory = root / "usr/lib/arm-linux-gnueabihf"
            directory.mkdir(parents=True)
            lib = directory / "libwebp.so.7"
            lib.write_bytes(b"\x7fELF\x00")
            def mocked_readelf(*argv):
                path = argv[-1]
                if "-hW" in argv:
                    return "Machine: ARM\nFlags: hard-float ABI\n"
                if "-A" in argv:
                    return ("Tag_FP_arch: VFPv3\nTag_Advanced_SIMD_arch: NEONv1"
                            if "libwebp" in path else "Tag_FP_arch: VFPv3-D16")
                return ("(NEEDED) Shared library: [libwebp.so.7]\n"
                        if path.endswith("/nura") else "")
            with patch.object(AUDIT, "run", side_effect=mocked_readelf):
                result = AUDIT.scan(root, app, full=False, objdump="unused")
            self.assertEqual(result["files_scanned"], 2)
            self.assertFalse(result["pass"])
            self.assertEqual(len(result["forbidden"]), 2)
            self.assertTrue(all("libwebp" in problem["path"]
                                for problem in result["forbidden"]))
            self.assertTrue(any("NEON attribute" in problem["reason"]
                                for problem in result["forbidden"]))

    def test_missing_dynamic_interpreter_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = root / "bin/nura"
            app.parent.mkdir(parents=True)
            app.write_bytes(b"\x7fELF" + b"\x00" * 10)
            def readelf(*argv):
                if "-hW" in argv:
                    return "Machine: ARM\nFlags: hard-float ABI\n"
                if "-A" in argv:
                    return "Tag_CPU_arch: v7\nTag_FP_arch: VFPv3-D16\n"
                if "-lW" in argv:
                    return "[Requesting program interpreter: /lib/ld-linux-armhf.so.3]"
                return ""
            with patch.object(AUDIT, "run", side_effect=readelf):
                result = AUDIT.scan(root, app, full=False, objdump="unused")
            self.assertFalse(result["pass"])
            self.assertEqual(result["missing"][0]["interpreter"], "/lib/ld-linux-armhf.so.3")

    def test_interpreter_included_in_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = root / "bin/nura"
            app.parent.mkdir(parents=True)
            app.write_bytes(b"\x7fELF" + b"\x00" * 10)
            loader = root / "lib/ld-linux-armhf.so.3"
            loader.parent.mkdir(parents=True)
            loader.write_bytes(b"\x7fELF" + b"\x00" * 10)
            def readelf(*argv):
                if "-hW" in argv:
                    return "Machine: ARM\nFlags: hard-float ABI\n"
                if "-A" in argv:
                    return "Tag_CPU_arch: v7\nTag_FP_arch: VFPv3-D16\n"
                if "-lW" in argv and argv[-1].endswith("/nura"):
                    return "[Requesting program interpreter: /lib/ld-linux-armhf.so.3]"
                return ""
            with patch.object(AUDIT, "run", side_effect=readelf):
                result = AUDIT.scan(root, app, full=False, objdump="unused")
            self.assertEqual(result["missing"], [])
            self.assertEqual(result["files_scanned"], 2)
            self.assertEqual(result["files"][0]["interpreter"], "/lib/ld-linux-armhf.so.3")
            self.assertFalse(result["pass"])

    def test_closure_cap_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = root / "bin/nura"
            app.parent.mkdir(parents=True)
            app.write_bytes(b"\x7fELF\x00")
            loader = root / "lib/ld-linux-armhf.so.3"
            loader.parent.mkdir(parents=True)
            loader.write_bytes(b"\x7fELF\x00")
            def readelf(*argv):
                if "-hW" in argv:
                    return "Machine: ARM\nFlags: hard-float ABI\n"
                if "-A" in argv:
                    return "Tag_FP_arch: VFPv3-D16"
                if "-lW" in argv and argv[-1].endswith("/nura"):
                    return "[Requesting program interpreter: /lib/ld-linux-armhf.so.3]"
                return ""
            with patch.object(AUDIT, "run", side_effect=readelf):
                with self.assertRaisesRegex(ValueError, "closure cap"):
                    AUDIT.scan(root, app, full=False, objdump="unused",
                               max_files=1)

    def test_symlinked_loader_cannot_escape_sysroot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = root / "bin/nura"
            app.parent.mkdir(parents=True)
            app.write_bytes(b"\x7fELF\x00")
            loader = root / "lib/ld-linux-armhf.so.3"
            loader.parent.mkdir(parents=True)
            loader.symlink_to("/etc/passwd")
            def readelf(*argv):
                if "-hW" in argv:
                    return "Machine: ARM\nFlags: hard-float ABI\n"
                if "-A" in argv:
                    return "Tag_FP_arch: VFPv3-D16\n"
                if "-lW" in argv:
                    return "[Requesting program interpreter: /lib/ld-linux-armhf.so.3]"
                return ""
            with patch.object(AUDIT, "run", side_effect=readelf):
                result = AUDIT.scan(root, app, full=False, objdump="unused")
            self.assertFalse(result["pass"])
            self.assertEqual(result["missing"][0]["interpreter"], "/lib/ld-linux-armhf.so.3")

    def test_attributes_only_must_never_claim_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = root / "nura"
            app.write_bytes(b"\x7fELF\x00")
            with patch.object(AUDIT, "run", side_effect=[
                "Machine: ARM\nhard-float ABI",
                "Tag_FP_arch: VFPv3-D16",
                "",
                "",
            ]):
                result = AUDIT.scan(root, app, full=False, objdump="unused")
            self.assertEqual(result["status"], "attributes-only")
            self.assertFalse(result["pass"])
