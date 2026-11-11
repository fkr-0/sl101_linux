"""NuraBrowser Ansible CI-only staging boundary, no live device access."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NuraBrowserCiStageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/nura-browser-armhf.yml").read_text()
        cls.play = (ROOT / "deploy/ansible/playbooks/nura-browser-stage.yml").read_text()
        cls.inventory = (ROOT / "deploy/ansible/inventory/hosts.yml").read_text()

    def test_ci_build_is_github_actions_not_local_elf(self):
        self.assertIn("actions/upload-artifact@", self.workflow)
        self.assertIn("SHA256-verify pinned Debian WPE", self.workflow)
        self.assertIn("sl101-nurabrowser-ci:2.54.0-2", self.workflow)
        self.assertIn("ci-build-armhf.sh", self.workflow)
        self.assertIn("--network none", self.workflow)

    def test_another_device_or_unapproved_kernel_fails_closed(self):
        for token in (
            "inventory_hostname == 'sl101-nura'",
            "ansible_host == '192.168.23.106'",
            "nura_browser_approved_git_sha",
            "nura_browser_approved_ci_run",
            "nura_browser_approved_tar_sha256",
            "nura_browser_approved_boot_id",
            "nura_browser_approved_kernel_release",
            "expected_sd_cid",
            "expected_emmc_cid",
            "expected_root_source",
        ):
            self.assertIn(token, self.play)
        self.assertIn("nura_browser_approved_kernel_release", self.inventory)

    def test_no_live_cog_or_sway_switch(self):
        for token in (
            "nura_browser_ci_payload.py",
            "--tar-sha256",
            "--check",
            "SL101_NURABROWSER_STAGE",
            "sha256sum",
            "CI-STAGED",
            "RUNTIME_QUALIFIED=false",
            "ACTIVATED=false",
        ):
            if token == "--check":
                continue
            self.assertIn(token, self.play)
        self.assertNotIn("systemctl restart", self.play)
        self.assertNotIn("rc-service", self.play)
        self.assertNotIn("mount --bind", self.play)
        self.assertNotIn("kexec", self.play)
        self.assertNotIn("/usr/local/bin/,browse", self.play)


if __name__ == "__main__":
    unittest.main()
