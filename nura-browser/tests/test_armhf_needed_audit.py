"""Legacy CLI delegates to the canonical fail-closed ARMHF ISA checker."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("legacy_needed_audit", ROOT / "packaging/audit-armhf-needed.py")
assert SPEC is not None and SPEC.loader is not None
legacy = module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)


def fake_readelf(*argv):
    elf = argv[-1]
    if "-hW" in argv:
        return "Machine: ARM\nFlags: Version5 EABI, hard-float ABI\n"
    if "-A" in argv:
        if elf.endswith("/libneon.so.0"):
            return "Tag_FP_arch: VFPv3\nTag_Advanced_SIMD_arch: NEONv1"
        if elf.endswith("/libvfp4.so.0"):
            return "Tag_FP_arch: VFPv4"
        return "Tag_FP_arch: VFPv3-D16"
    if "-lW" in argv:
        return ""
    if elf.endswith("/app") and "-dW" in argv:
        return "(NEEDED) Shared library: [libneon.so.0]\n"
    return ""


class NeededCompatibilityTests(TestCase):
    def create_elf(self, root: Path, path: str) -> Path:
        f = root / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\x7fELF" + b"\x00" * 32)
        return f

    def test_attributes_clean_not_release_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            app = self.create_elf(root, "app")
            with patch.object(legacy.canonical, "run", return_value="Machine: ARM\nhard-float ABI\nTag_FP_arch: VFPv3-D16"):
                result = legacy.closure(app, root=root)
            self.assertTrue(result["attributes_clean"])
            self.assertFalse(result["pass"])
            self.assertFalse(result["qualifies_full_instruction_closure"])
            self.assertFalse(result["qualifies_runtime_or_device"])

    def test_legacy_cli_fails_neon_and_non_d16(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            app = self.create_elf(root, "app")
            self.create_elf(root, "usr/lib/arm-linux-gnueabihf/libneon.so.0")
            with patch.object(legacy.canonical, "run", side_effect=fake_readelf):
                report = legacy.closure(app, root=root)
            self.assertFalse(report["attributes_clean"])
            self.assertFalse(report["pass"])
            self.assertEqual(report["elf_count"], 2)
            self.assertTrue(any("NEON" in p for item in report["unsafe"]
                                for p in item["problems"]))
            self.assertTrue(any("VFPv3" in p for item in report["unsafe"]
                                for p in item["problems"]))

    def test_missing_dependency_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            app = self.create_elf(root, "app")
            def no_soname(*argv):
                if "-dW" in argv:
                    return "(NEEDED) Shared library: [libmissing.so.0]"
                return fake_readelf(*argv)
            with patch.object(legacy.canonical, "run", side_effect=no_soname):
                report = legacy.closure(app, root=root)
            self.assertFalse(report["attributes_clean"])
            self.assertFalse(report["pass"])
            self.assertEqual(report["missing"][0]["needed"], "libmissing.so.0")

    def test_custom_search_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            app = self.create_elf(root, "app")
            self.create_elf(root, "custom/libneon.so.0")
            with patch.object(legacy.canonical, "run", side_effect=fake_readelf):
                report = legacy.closure(app, directories=[Path("/custom")], root=root)
            self.assertEqual(report["elf_count"], 2)
            self.assertEqual(report["missing"], [])

    def test_vfp4_is_rejected_without_neon_attribute(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            app = self.create_elf(root, "app")
            self.create_elf(root, "usr/lib/arm-linux-gnueabihf/libvfp4.so.0")
            def vfp4_needed(*argv):
                if "-dW" in argv and argv[-1].endswith("/app"):
                    return "(NEEDED) Shared library: [libvfp4.so.0]"
                return fake_readelf(*argv)
            with patch.object(legacy.canonical, "run", side_effect=vfp4_needed):
                report = legacy.closure(app, root=root)
            self.assertFalse(report["pass"])
            self.assertTrue(any("VFPv4" in p for item in report["unsafe"]
                                for p in item["problems"]))
