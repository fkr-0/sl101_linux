"""CI provenance/tar verifier: hostile local fixtures, no devices or GitHub."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify-ci-release.py"
spec = importlib.util.spec_from_file_location("browser_verify_ci", SCRIPT)
verify_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_module)

SOURCE_SHA = "a" * 40
RUN_ID = "42999999999"
CORE = b"\x7fELF" + b"A" * 96  # ELF-specific validation mocked only in these fixtures.
LAUNCHER = b"#!/bin/sh\n# NURABROWSER_PRIVATE_ROOT\n"


class CiReleaseVerifierTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="browser-ci-verifier-")
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.receipt = {
            "schema": "sl101.nurabrowser.github-ci.v1",
            "source_repo": "fkr-0/sl101_linux",
            "source_sha": SOURCE_SHA,
            "run_id": RUN_ID,
            "run_attempt": 1,
            "wpe_debian_version": "2.54.0-2",
            "target": "armv7-linux-gnueabihf-vfpv3-d16-no-neon",
            "status": "static-armhf-audited-not-runtime-qualified",
            "browser_sha256": verify_module.digest(CORE),
            "launcher_sha256": verify_module.digest(LAUNCHER),
        }
        self.manifest = {
            "status": "static-armhf-audited-not-runtime-qualified",
            "wpe_debian_version": "2.54.0-2",
            "artifacts": [
                {
                    "install_path": "/usr/libexec/nura-browser/nurabrowser-core",
                    "sha256": verify_module.digest(CORE),
                    "size": len(CORE),
                },
                {
                    "install_path": "/usr/bin/,browse",
                    "sha256": verify_module.digest(LAUNCHER),
                    "size": len(LAUNCHER),
                },
            ],
        }
        self.make_artifact()

    def make_artifact(self, *, malicious=None):
        members = {
            "release/bin/nurabrowser-core": CORE,
            "release/bin/,browse": LAUNCHER,
            "release/CI-PROVENANCE.json": json.dumps(self.receipt).encode(),
            "release/nurabrowser-artifacts.json": json.dumps(self.manifest).encode(),
        }
        with tarfile.open(self.out / "nurabrowser-ci.tar", "w") as tar:
            for d in ("release", "release/bin"):
                info = tarfile.TarInfo(d)
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            for name, content in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = 0o755 if name.startswith("release/bin/") else 0o644
                tar.addfile(info, io.BytesIO(content))
            if malicious:
                info = tarfile.TarInfo(malicious)
                info.type = tarfile.SYMTYPE
                info.linkname = "../../etc/passwd"
                tar.addfile(info)
        digest = verify_module.digest((self.out / "nurabrowser-ci.tar").read_bytes())
        (self.out / "SHA256SUMS.txt").write_text(
            f"{digest}  nurabrowser-ci.tar\n"
        )
        (self.out / "BIN-SHA256SUMS.txt").write_text(
            f"{verify_module.digest(CORE)}  release/bin/nurabrowser-core\n"
            f"{verify_module.digest(LAUNCHER)}  release/bin/,browse\n"
        )
        (self.out / "NO-NEON-QEMU.txt").write_text(
            "HWCAP=0x0000e8d7 NEON=0\nTEGRA2_NO_NEON_QEMU_PROBE=PASS\n"
        )
        (self.out / "ELF-NEEDED.txt").write_text(
            "Shared library: [libWPEWebKit-2.0.so.1]\n"
        )
        for name in verify_module.EVIDENCE - {
            "nurabrowser-ci.tar", "SHA256SUMS.txt",
            "BIN-SHA256SUMS.txt", "NO-NEON-QEMU.txt", "ELF-NEEDED.txt",
        }:
            (self.out / name).write_text("provenance fixture\n")
        self.tar_sha = digest

    def verify(self, **overrides):
        data = dict(artifact_dir=self.out, sha=SOURCE_SHA,
                    run_id=RUN_ID, tar_sha=self.tar_sha)
        data.update(overrides)
        with patch.object(verify_module, "checked_armhf") as elf:
            result = verify_module.verify(**data)
            elf.assert_called_once_with(CORE)
            return result

    def test_exact_release(self):
        result = self.verify()
        self.assertEqual(result["status"], "CI-STATIC-READY-RUNTIME-UNQUALIFIED")

    def test_reject_local_unapproved_artifact(self):
        with self.assertRaisesRegex(ValueError, "approved SHA256"):
            self.verify(tar_sha="f" * 64)

    def test_reject_incorrect_source_sha(self):
        with self.assertRaisesRegex(ValueError, "source_sha"):
            self.verify(sha="b" * 40)

    def test_reject_incorrect_run_id(self):
        with self.assertRaisesRegex(ValueError, "run_id"):
            self.verify(run_id="123")

    def test_reject_malicious_symlink_member(self):
        self.make_artifact(malicious="release/bin/link")
        with self.assertRaisesRegex(ValueError, "archive entries"):
            self.verify()

    def test_reject_modified_binary_digest(self):
        self.receipt["browser_sha256"] = "0" * 64
        self.make_artifact()
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.verify()

    def test_reject_missing_no_neon_probe(self):
        (self.out / "NO-NEON-QEMU.txt").write_text("NEON=1\n")
        with self.assertRaisesRegex(ValueError, "no-NEON"):
            self.verify()

    def test_prepared_two_extra_receipts_allowed_but_no_other_files(self):
        (self.out / "CI-GITHUB-RUN.json").write_text("{}\n")
        (self.out / "CI-VERIFIED.json").write_text("{}\n")
        self.verify()
        (self.out / "unknown.exe").write_bytes(b"untrusted")
        with self.assertRaisesRegex(ValueError, "evidence file set"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
