"""No-device negative gates for CI-only native headless qualifier."""
import pathlib
import re
import subprocess
import unittest


PROJECT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = PROJECT / "scripts/run-staged-ci-smoke.sh"
PRIVATE_RUNNER = PROJECT / "scripts/qualify-cog-runtime-headless.sh"


class StagedCiHeadlessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = RUNNER.read_text()

    def test_posix_shell_syntax(self):
        result = subprocess.run(
            ["sh", "-n", str(RUNNER)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_mode_fails_without_device_contact(self):
        for args in ([], ["--upgrade"], ["--check", "--run"]):
            with self.subTest(args=args):
                result = subprocess.run(
                    ["sh", str(RUNNER), *args], capture_output=True,
                    text=True, timeout=4
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("REFUSED", result.stderr)

    def test_uses_only_approved_github_ci_artifact(self):
        src = self.text
        for word in (
            "ci_run=43032042301",
            "core_hash=67b5a5d6961ccb4ee100e40a6cb8300571e6a986978fd20e2fd20381a2e3a06b",
            "tar_hash=a15c922ac9e8e49a499e4b128c42cadbfb4ce96f5e44d2ecf2acc1dc8259920a",
            "RUNTIME_QUALIFIED=false",
            "ACTIVATED=false",
            "NURABROWSER_NATIVE_HEADLESS_TEST",
            'install -m 0755 "$rel/release/bin/nurabrowser-core"',
        ):
            self.assertIn(word, src)
        self.assertNotIn("curl ", src)
        self.assertNotIn("wget ", src)
        self.assertNotIn("meson ", src)

    def test_exact_qualifier_hash(self):
        import hashlib
        digest = hashlib.sha256(PRIVATE_RUNNER.read_bytes()).hexdigest()
        self.assertIn(f"runner_hash={digest}", self.text)

    def test_read_only_preflight_never_writes(self):
        src = self.text
        self.assertLess(src.index('if [ "$action" = --check ]'),
                        src.index('stage=$(mktemp -d'))
        self.assertLess(src.index('if [ "$action" = --check ]'),
                        src.index('sh "$runner" "$stage" "$core_hash"'))

    def test_hardware_identity_and_no_sandbox_bypass(self):
        src = self.text
        for word in (
            "expected_boot_id=",
            "expected_kernel=",
            "expected_sd_cid=",
            "expected_emmc_cid=",
            "pgrep -x nurabrowser-core",
            'sh "$runner" --preflight "$stage" "$core_hash"',
        ):
            self.assertIn(word, src)
        self.assertNotIn("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1", src)
        self.assertNotIn("mount --bind", src)
        self.assertNotRegex(src, r"(?m)^\s*(?:sudo\s+)?(?:/sbin/)?reboot(?:\s|$)")


if __name__ == "__main__":
    unittest.main()
