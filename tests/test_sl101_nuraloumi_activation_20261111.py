"""Offline activation and rollback tests, never touch real SL101 devices."""
import importlib.util
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/ansible/tools/nuraloumi_activate.py"
spec = importlib.util.spec_from_file_location("nura_activate", SCRIPT)
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)

SHA = "f" * 40
NAMES = sorted(activation.REQUIRED | {f"nuraloumi-tool-{i:02d}" for i in range(18)})


def fake_install(home):
    home = Path(home)
    root = home / "opt/nuraloumi"
    cli = home / "usr/local/bin"
    cli.mkdir(parents=True)
    old = root / "releases/working-before-ci"
    old.mkdir(parents=True)
    (old / "nuraloumi-panel").write_text("old-binary")
    root.mkdir(parents=True, exist_ok=True)
    (root / "current").symlink_to(old)
    (cli / "nuraloumi-sway-workspace-switcher").write_bytes(b"original-switcher")
    new = root / "releases" / SHA
    (new / "bin").mkdir(parents=True)
    expected = []
    for n in NAMES:
        binary = new / "bin" / n
        binary.write_bytes(("FAKE_BIN_" + n).encode())
        binary.chmod(0o755)
        expected.append(f"{activation.sha256(binary)}  bin/{n}")
    (new / "SHA256SUMS.bin").write_text("\n".join(expected) + "\n")
    (new / "MANIFEST.txt").write_text(
        f"git_commit={SHA}\n"
        "git_dirty=false\n"
        f"target={activation.ARM}\n"
        f"binaries={','.join(NAMES)}\n"
        "files:\n"
    )
    (new / "CI-READY").write_text(f"GIT_SHA={SHA}\nABI={activation.ARM}\nACTIVATED=false\n")
    return activation.Activation(root, cli, SHA, expected_old=old), root, cli, old, new


class ActivationTests(unittest.TestCase):
    def test_full_suite_links_are_atomic_and_rollback_restores_original_switcher(self):
        with tempfile.TemporaryDirectory() as d, patch.object(activation.os, "geteuid", return_value=0):
            tool, root, cli, old, release = fake_install(d)
            self.assertEqual(tool.preview()["binaries"], 24)
            self.assertEqual((root / "current").resolve(), old)
            tool.activate()
            tool.verify_links()
            self.assertEqual((root / "current").resolve(), release / "bin")
            self.assertEqual(len([p for p in cli.iterdir() if p.name.startswith("nuraloumi-")]), 24)
            self.assertEqual(tool.preview()["result"], "already-active")
            self.assertEqual((release / "activation-backup/nuraloumi-sway-workspace-switcher").read_bytes(),
                             b"original-switcher")
            tool.activate()
            tool.rollback()
            self.assertEqual((root / "current").resolve(), old)
            self.assertEqual((cli / "nuraloumi-sway-workspace-switcher").read_bytes(), b"original-switcher")
            self.assertFalse((cli / "nuraloumi-panel").exists())
            self.assertFalse((cli / "nuraloumi-run").exists())
            self.assertEqual(len(list(release.glob("bin/*"))), 24)

    def test_foreign_executable_collision_is_refused_without_any_mutation(self):
        with tempfile.TemporaryDirectory() as d, patch.object(activation.os, "geteuid", return_value=0):
            tool, root, cli, old, release = fake_install(d)
            (cli / "nuraloumi-panel").write_text("foreign")
            with self.assertRaisesRegex(ValueError, "foreign executable collision"):
                tool.activate()
            self.assertEqual((root / "current").resolve(), old)
            self.assertFalse(tool.journal.exists())
            self.assertEqual((cli / "nuraloumi-panel").read_text(), "foreign")

    def test_wrong_previous_release_is_refused(self):
        with tempfile.TemporaryDirectory() as d, patch.object(activation.os, "geteuid", return_value=0):
            tool, root, cli, old, release = fake_install(d)
            tool.expected_old = root / "releases/unknown"
            with self.assertRaisesRegex(ValueError, "reviewed old release"):
                tool.preview()

    def test_tampered_binary_fails_before_touching_current(self):
        with tempfile.TemporaryDirectory() as d, patch.object(activation.os, "geteuid", return_value=0):
            tool, root, cli, old, release = fake_install(d)
            (release / "bin/nuraloumi-panel").write_bytes(b"substituted")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                tool.activate()
            self.assertEqual((root / "current").resolve(), old)

    def test_late_binary_corruption_does_not_block_restoration(self):
        with tempfile.TemporaryDirectory() as d, patch.object(activation.os, "geteuid", return_value=0):
            tool, root, cli, old, release = fake_install(d)
            tool.activate()
            (release / "bin/nuraloumi-panel").write_bytes(b"corrupt after activation")
            tool.rollback()
            self.assertEqual((root / "current").resolve(), old)
            self.assertEqual((cli / "nuraloumi-sway-workspace-switcher").read_bytes(),
                             b"original-switcher")

    def test_activator_playbook_has_separate_gates_and_rescue(self):
        book = (ROOT / "deploy/ansible/playbooks/nuraloumi-activate.yml").read_text()
        self.assertIn("import_playbook: nuraloumi-stage.yml", book)
        self.assertIn("SL101_NURALOUMI_ACTIVATE", book)
        self.assertIn("nuraloumi_previous_current", book)
        self.assertIn("become: true", book)
        self.assertIn("rollback", book)
        self.assertIn("sl101-sway-panel", book)
        self.assertNotIn("swaymsg reload", book)
        self.assertNotIn("reboot", book)
        self.assertNotIn("apk add", book)

    def test_manual_rollback_is_a_separately_gated_ansible_playbook(self):
        book = (ROOT / "deploy/ansible/playbooks/nuraloumi-rollback.yml").read_text()
        self.assertIn("hosts: sl101-nura", book)
        self.assertIn("SL101_NURALOUMI_ROLLBACK", book)
        self.assertIn("SL101_APPLY", book)
        self.assertIn("nuraloumi_approved_git_sha", book)
        self.assertIn("('EMMC_CID=' ~ expected_emmc_cid)", book)
        self.assertIn("('SD_CID=' ~ expected_sd_cid)", book)
        self.assertIn("('ROOT=' ~ expected_root_source)", book)
        self.assertIn("nura_activation_tool", book)
        self.assertIn("OLD_PANEL_RESTORED", book)
        self.assertNotIn("reboot", book)


if __name__ == "__main__":
    unittest.main()
