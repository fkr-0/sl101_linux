"""Host-only checks of pinned ARMHF WPE dev image preparation.

These tests do not contact devices, fetch packages or run Docker builds.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "packaging/Dockerfile.armhf-wpe-dev").read_text()
SCRIPT = (ROOT / "packaging/prepare-armhf-sysroot.sh").read_text()


class ArmhfSysrootPreparationTests(unittest.TestCase):
    def test_exact_debian_wpe_version(self):
        self.assertIn("libwpewebkit-2.0-1_2.54.0-2_armhf.deb", DOCKERFILE)
        self.assertIn("libwpewebkit-2.0-dev_2.54.0-2_armhf.deb", DOCKERFILE)
        self.assertGreaterEqual(DOCKERFILE.count("= '2.54.0-2'"), 2)
        self.assertIn("unstable main", DOCKERFILE)

    def test_archive_verification_before_container(self):
        self.assertRegex(SCRIPT, r"runtime_sha=[a-f0-9]{64}\n")
        self.assertRegex(SCRIPT, r"dev_sha=[a-f0-9]{64}\n")
        self.assertLess(SCRIPT.index("sha256sum -c -"),
                        SCRIPT.index("docker build"))

    def test_docker_isolation(self):
        self.assertIn("--pull=false", SCRIPT)
        self.assertIn("--network none", SCRIPT)
        self.assertIn("dst=/src,readonly", SCRIPT)
        self.assertIn("dst=/out", SCRIPT)
        self.assertIn("--user", SCRIPT)
        self.assertIn("--image-only", SCRIPT)

    def test_no_device_or_root_modification(self):
        for forbidden in (
            "ssh ", "scp ", "reboot ", "flash ", "kexec ",
            "docker system prune", "docker volume prune",
            "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, SCRIPT.lower())
        self.assertNotIn("apt-get install", SCRIPT)
        self.assertIn("apt-get install", DOCKERFILE)

    def test_crossbuild_not_suppressed(self):
        self.assertIn("scripts/build-armhf.sh / /out/build", SCRIPT)
        self.assertIn("libglib2.0-dev:armhf", DOCKERFILE)
        self.assertIn("libjson-glib-dev:armhf", DOCKERFILE)
        self.assertIn("FROM sl101-wpe-armhf-builder:20261003", DOCKERFILE)


if __name__ == "__main__":
    unittest.main()
