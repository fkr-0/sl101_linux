"""Host-only integrity regression tests for the SL101 dmafix1 candidate packager."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sl101-prod-dmafix1-candidate.py"
spec = importlib.util.spec_from_file_location("sl101_dmafix1_candidate", SCRIPT)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class IntegrityTests(unittest.TestCase):
    def test_safe_relative_paths(self):
        for path in ("/etc/shadow", "../escape", "a/../../escape", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                candidate.safe_relative(path)
        self.assertEqual(candidate.safe_relative("boot/zImage"), Path("boot/zImage"))

    def test_sha256_index_requires_all_files_and_checks_digests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "boot").mkdir()
            artifact = root / "boot" / "zImage"
            artifact.write_bytes(b"kernel")
            candidate.write_sums(root)
            self.assertEqual(candidate.verify_sums(root), 1)
            artifact.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                candidate.verify_sums(root)

    def test_unlisted_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").write_text("a")
            candidate.write_sums(root)
            (root / "b").write_text("b")
            with self.assertRaisesRegex(ValueError, "incomplete checksums"):
                candidate.verify_sums(root)

    def test_duplicate_checksum_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").write_text("a")
            candidate.write_sums(root)
            index = root / "SHA256SUMS"
            index.write_text(index.read_text() * 2)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                candidate.verify_sums(root)

    def test_absolute_symlink_is_not_allowed_in_distributable_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod = root / candidate.MODULE_SUBDIR
            mod.mkdir(parents=True)
            (mod / "build").symlink_to("/host/private/build")
            candidate.inspect_symlinks(root, allow_build=True)
            with self.assertRaisesRegex(ValueError, "unexpected symlink"):
                candidate.inspect_symlinks(root, allow_build=False)

    def test_real_candidate_source_artifacts_without_ephemeral_source_tree(self):
        # No volatile /tmp source tree is required for post-build verification.
        if not candidate.LANE.exists():
            self.skipTest("device build evidence not installed in this checkout")
        manifest = candidate.verify_inputs()
        self.assertEqual(manifest["modules"], 587)
        self.assertGreater(manifest["checksummed_files"], 580)


if __name__ == "__main__":
    unittest.main()
