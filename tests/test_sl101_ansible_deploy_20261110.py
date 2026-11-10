"""Offline guards for containerized SL101 Ansible and hard comma namespace."""
import re
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy/ansible"


class AnsibleDeployTests(unittest.TestCase):
    def test_compose_overrides_are_valid_and_nonprivileged(self):
        base = (DEPLOY / "compose.yaml").read_text()
        self.assertIn("read_only: true", base)
        self.assertIn("cap_drop: [ALL]", base)
        self.assertIn("no-new-privileges:true", base)
        self.assertIn("../../:/workspace:ro", base)
        self.assertIn("./inventory:/inventory:ro", base)
        self.assertIn("./data:/data:ro", base)
        self.assertIn("/home/deploy/.ssh:ro", base)
        self.assertNotIn("privileged: true", base)
        self.assertNotIn("/var/run/docker.sock", base)
        for file, profile, target in (
            ("compose.nura.yaml", "nura", "sl101-nura"),
            ("compose.debian.yaml", "debian", "sl101-debian"),
        ):
            text = (DEPLOY / file).read_text()
            self.assertIn("DEPLOY_PROFILE: " + profile, text)
            self.assertIn("DEPLOY_TARGET: " + target, text)

    def test_entrypoint_is_check_by_default_and_apply_is_explicit(self):
        code = (DEPLOY / "entrypoint.sh").read_text()
        self.assertIn('check) set -- --check --diff', code)
        self.assertIn('[ "${SL101_APPLY:-NO}" = YES ]', code)
        self.assertIn("ansible-playbook", code)
        self.assertIn('--limit "$DEPLOY_TARGET"', code)
        self.assertNotIn('StrictHostKeyChecking=no', code)
        r = subprocess.run(["sh", "-n", str(DEPLOY / "entrypoint.sh")], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_physical_identity_check_precedes_any_writes(self):
        book = (DEPLOY / "playbooks/site.yml").read_text()
        self.assertLess(book.index("Read exact physical identity"), book.index("include_tasks: user-commands.yml"))
        self.assertIn("expected_sd_cid | length == 32", book)
        self.assertIn("fail_msg:", book)
        self.assertNotIn("ignore_errors: true", book)

    def test_two_distinct_devices_fail_closed(self):
        inventory = (DEPLOY / "inventory/hosts.yml").read_text()
        self.assertIn("192.168.23.106", inventory)
        self.assertIn("192.168.23.100", inventory)
        self.assertIn('035344534c31323880ac79a543010300', inventory)
        self.assertIn('03534453553332478030be3f6400b900', inventory)
        self.assertIn("expected_hostname: sl101-nura", inventory)

    def test_public_commands_canonical_no_alias_manifest(self):
        entries = list((DEPLOY / "public/nura").iterdir())
        self.assertTrue(entries)
        for path in entries:
            with self.subTest(path=path):
                self.assertRegex(path.name, r"^,[a-z][a-z0-9-]*$")
                self.assertTrue(path.is_file())
                source = path.read_text()
                self.assertTrue(source.startswith("#!/bin/sh\n# SL101 public command:"))
                self.assertEqual(subprocess.run(["sh", "-n", str(path)]).returncode, 0)
        for forbidden in ("aliases.yml", "commands-manifest.yml", "compat-symlinks.yml"):
            self.assertFalse((DEPLOY / forbidden).exists())
        tasks = (DEPLOY / "playbooks/user-commands.yml").read_text()
        self.assertIn("fileglob", tasks)
        self.assertNotIn("sl101-compat", tasks)

    def test_no_device_mutations_in_offline_test_path(self):
        for path in [DEPLOY / "entrypoint.sh", DEPLOY / "public/nura/,renderer-status"]:
            text = path.read_text()
            for forbidden in ("kexec ", "reboot ", "dd if=", "fw_setenv", "ssh -o StrictHostKeyChecking=no"):
                self.assertNotIn(forbidden, text)

    def test_host_compose_and_ansible_syntax_when_installed(self):
        cp = subprocess.run(["docker", "compose", "-f", str(DEPLOY / "compose.yaml"),
                             "-f", str(DEPLOY / "compose.nura.yaml"), "config", "--quiet"],
                            capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        cp = subprocess.run(["ansible-playbook", "-i", str(DEPLOY / "inventory/hosts.yml"),
                             str(DEPLOY / "playbooks/site.yml"), "--syntax-check"],
                            capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0, cp.stderr)


if __name__ == "__main__":
    unittest.main()
