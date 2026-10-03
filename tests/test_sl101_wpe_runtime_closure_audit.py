import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sl101-wpe-runtime-closure-audit.py"

spec = importlib.util.spec_from_file_location("closure_audit", SCRIPT)
closure_audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(closure_audit)


def status_text(include_webp=True):
    blocks = [
        """Package: libwpewebkit-2.0-1
Status: install ok installed
Version: 2.54.0-2
Depends: libc6 (>= 2.43), libwebp7 (>= 1.6.0), libpng16-16t64
""",
        """Package: cog
Status: install ok installed
Version: 0.18.5-1
Depends: libwpewebkit-2.0-1
""",
        """Package: libc6
Status: install ok installed
Version: 2.43-6
""",
        """Package: libpng16-16t64
Status: install ok installed
Version: 1.6
""",
    ]
    if include_webp:
        blocks.append(
            """Package: libwebp7
Status: install ok installed
Version: 1.6.0
Depends: libc6
"""
        )
    return "\n".join(blocks)


class WPERuntimeClosureAuditTests(unittest.TestCase):
    def make_root(self, include_webp=True):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        status = root / "var/lib/dpkg/status"
        status.parent.mkdir(parents=True)
        status.write_text(status_text(include_webp), encoding="utf-8")
        packages = closure_audit.parse_dpkg_status(status.read_text())
        closure, _, _ = closure_audit.resolve_package_closure(
            packages, ["libwpewebkit-2.0-1", "cog"]
        )
        info = root / "var/lib/dpkg/info"
        info.mkdir(parents=True)
        for name in closure:
            (info / f"{name}.list").write_text(
                f"/usr/lib/{name}.so\n", encoding="utf-8"
            )
        return td, root, packages

    @staticmethod
    def fake_elf(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x7fELF" + b"\0" * 28)

    def test_complete_transitive_runtime_can_pass(self):
        td, root, packages = self.make_root()
        try:
            self.fake_elf(root / "usr/lib/libWPEWebKit.so")
            self.fake_elf(root / "usr/lib/libwebp.so.7")
            raw = {
                "records": [
                    {"path": "usr/lib/libWPEWebKit.so", "issues": []},
                    {"path": "usr/lib/libwebp.so.7", "issues": []},
                ]
            }
            result = closure_audit.evaluate(
                root, packages, raw, ["libwpewebkit-2.0-1", "cog"], set()
            )
            self.assertTrue(result["pass"], result)
            self.assertIn("libwebp7", result["package_closure"]["packages"])
        finally:
            td.cleanup()

    def test_omitted_transitive_elf_fails_closed(self):
        td, root, packages = self.make_root()
        try:
            self.fake_elf(root / "usr/lib/libWPEWebKit.so")
            self.fake_elf(root / "usr/lib/libwebp.so.7")
            raw = {"records": [{"path": "usr/lib/libWPEWebKit.so", "issues": []}]}
            result = closure_audit.evaluate(
                root, packages, raw, ["libwpewebkit-2.0-1", "cog"], set()
            )
            self.assertFalse(result["pass"])
            self.assertEqual(
                result["elf_coverage"]["missing_audit_records"],
                ["usr/lib/libwebp.so.7"],
            )
        finally:
            td.cleanup()

    def test_missing_transitive_package_fails_closed(self):
        td, root, packages = self.make_root(include_webp=False)
        try:
            result = closure_audit.evaluate(
                root, packages, {"records": []}, ["libwpewebkit-2.0-1", "cog"], set()
            )
            self.assertFalse(result["pass"])
            missing = result["package_closure"]["missing_dependency_groups"]
            self.assertTrue(
                any(item["alternatives"] == ["libwebp7"] for item in missing), missing
            )
        finally:
            td.cleanup()

    def test_explicit_failure_allowlist_is_narrow(self):
        td, root, packages = self.make_root()
        try:
            helper = root / "usr/lib/gst-ptp-helper"
            self.fake_elf(helper)
            raw = {
                "records": [
                    {
                        "path": "usr/lib/gst-ptp-helper",
                        "issues": ["vfp-d16-d31-register"],
                    }
                ]
            }
            result = closure_audit.evaluate(
                root,
                packages,
                raw,
                ["libwpewebkit-2.0-1", "cog"],
                {"usr/lib/gst-ptp-helper"},
            )
            self.assertTrue(result["pass"], result)
            self.assertIn(
                "usr/lib/gst-ptp-helper", result["isa_failures"]["allowed"]
            )
        finally:
            td.cleanup()

    def test_unknown_failure_remains_fatal(self):
        td, root, packages = self.make_root()
        try:
            bad = root / "usr/lib/libbad.so"
            self.fake_elf(bad)
            raw = {
                "records": [
                    {
                        "path": "usr/lib/libbad.so",
                        "issues": ["neon-only-mnemonic:vst1"],
                    }
                ]
            }
            result = closure_audit.evaluate(
                root, packages, raw, ["libwpewebkit-2.0-1", "cog"], set()
            )
            self.assertFalse(result["pass"])
            self.assertIn("usr/lib/libbad.so", result["isa_failures"]["unexpected"])
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
