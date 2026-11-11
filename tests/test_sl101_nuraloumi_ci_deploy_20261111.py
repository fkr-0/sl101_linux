"""Offline-only CI-provenance and Ansible staging safety regressions for .106."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy/ansible"
TOOL = DEPLOY / "tools/nuraloumi_ci_payload.py"
SPEC = importlib.util.spec_from_file_location("nura_ci_payload", TOOL)
PAYLOAD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAYLOAD)
SHA = "f" * 40
RUN = 1234567
NAMES = sorted(PAYLOAD.REQUIRED | {f"nuraloumi-test-{i:02d}" for i in range(19)})


def make_fixture(root):
    """Synthetic ELF32 ARMHF bytes, NEVER a release CI artifact."""
    root = Path(root)
    (root / "release/bin").mkdir(parents=True, exist_ok=True)
    header = bytearray(52)
    header[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<H", header, 18, 40)
    struct.pack_into("<I", header, 36, 0x5000400)
    sums = {}
    for i, name in enumerate(NAMES):
        p = root / "release/bin" / name
        p.write_bytes(header + i.to_bytes(4, "little"))
        p.chmod(0o755)
        sums["bin/" + name] = PAYLOAD.sha256(p)
    manifest = (
        "schema=nuraloumi-package-manifest-v1\n"
        "version=0.0.4-dev.2\n"
        f"target={PAYLOAD.TARGET}\n"
        f"git_commit={SHA}\n"
        "git_dirty=false\n"
        f"binaries={','.join(NAMES)}\n"
        "files:\n"
        + "".join(f"  {sums[p]}  {p}\n" for p in sums)
    )
    (root / "release/MANIFEST.txt").write_text(manifest)
    (root / "release/SHA256SUMS.bin").write_text(
        "".join(f"{sums['bin/' + n]}  bin/{n}\n" for n in NAMES)
    )
    with tarfile.open(root / "nuraloumi-ci.tar", "w") as archive:
        for path in sorted((root / "release").rglob("*")):
            archive.add(path, arcname=path.relative_to(root / "release"))
    (root / "ELF-AUDIT.txt").write_text("SYNTHETIC TEST, NOT AN AUDIT\n")
    (root / "CI-PROVENANCE.json").write_text(json.dumps({
        "schema": PAYLOAD.SCHEMA,
        "git_sha": SHA,
        "run_id": RUN,
        "target": PAYLOAD.TARGET,
        "ci_conclusion": "success",
        "ci_tar_sha256": PAYLOAD.sha256(root / "nuraloumi-ci.tar"),
        "manifest_sha256": PAYLOAD.sha256(root / "release/MANIFEST.txt"),
        "binaries": NAMES,
        "synthetic_test_only": True,
    }))
    return root


def fake_root_playbook(folder, stage, install_base):
    play = folder / "offline-stage.yml"
    tasks = DEPLOY / "playbooks/nuraloumi-stage-tasks.yml"
    play.write_text(
        "- hosts: localhost\n"
        "  connection: local\n"
        "  gather_facts: false\n"
        "  vars:\n"
        f"    nura_ci_payload: '{stage}'\n"
        f"    nura_ci_sha: '{SHA}'\n"
        f"    nura_ci_run: '{RUN}'\n"
        f"    nura_install_base: '{install_base}'\n"
        f"    nura_release_root: '{install_base}/releases/{SHA}'\n"
        "    sl101_molecule: true\n"
        "  tasks:\n"
        f"    - ansible.builtin.include_tasks: '{tasks}'\n"
    )
    return play


class NuraCiAnsibleTests(unittest.TestCase):
    def test_controller_rejects_modified_binary_or_forged_release_digest(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_fixture(Path(d) / "payload")
            self.assertEqual(PAYLOAD.verify_payload(root, SHA, RUN), NAMES)
            with self.assertRaisesRegex(ValueError, "immutable digest"):
                PAYLOAD.verify_payload(root, SHA, RUN, "b" * 64)
            with self.assertRaisesRegex(ValueError, "immutable digest"):
                PAYLOAD.verify_payload(root, SHA, RUN, "a" * 64, "b" * 64)
            (root / "release/bin/nuraloumi-panel").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "ELF32"):
                PAYLOAD.verify_payload(root, SHA, RUN)

    def test_offline_ansible_stage_read_only_preview_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            stage = make_fixture(folder / "payload")
            install = folder / "fake-device/opt/nuraloumi"
            play = fake_root_playbook(folder, stage, install)
            base = ["ansible-playbook", "-i", "localhost,", str(play)]
            preview = subprocess.run(base + ["--check"], capture_output=True, text=True)
            self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
            self.assertFalse(install.exists(), "dry run wrote to fake device")
            # Existing .106 installation parent directories have setgid and
            # a non-root group. New releases must never normalize them.
            releases = install / "releases"
            releases.mkdir(parents=True)
            install.chmod(0o2755)
            releases.chmod(0o2755)
            parent_modes = (install.stat().st_mode & 0o7777,
                            releases.stat().st_mode & 0o7777)
            first = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(parent_modes, (install.stat().st_mode & 0o7777,
                                            releases.stat().st_mode & 0o7777))
            release = install / "releases" / SHA
            self.assertEqual(len(list((release / "bin").iterdir())), 24)
            self.assertIn("ACTIVATED=false", (release / "CI-READY").read_text())
            result = subprocess.run(["sha256sum", "--strict", "--check", "SHA256SUMS.bin"],
                                    cwd=release, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            second = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertRegex(second.stdout, r"changed=0\s+")
            # Never create or replace a current symlink or compositor config.
            self.assertFalse((install / "current").exists())

    def test_existing_symlink_staging_parent_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            stage = make_fixture(folder / "payload")
            outside = folder / "outside"
            outside.mkdir()
            install = folder / "fake-device/opt/nuraloumi"
            install.parent.mkdir(parents=True)
            install.symlink_to(outside, target_is_directory=True)
            play = fake_root_playbook(folder, stage, install)
            run = subprocess.run(["ansible-playbook", "-i", "localhost,", str(play)],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("Refusing unexpected symlink", run.stdout + run.stderr)
            self.assertEqual(list(outside.iterdir()), [])

    def test_live_inventory_and_two_gate_entrypoint(self):
        inventory = (DEPLOY / "inventory/hosts.yml").read_text()
        book = (DEPLOY / "playbooks/nuraloumi-stage.yml").read_text()
        entry = (DEPLOY / "entrypoint.sh").read_text()
        self.assertIn("192.168.23.106", inventory)
        self.assertIn("expected_root_source: \"/dev/mmcblk1p1\"", inventory)
        self.assertIn("7001004d4d43333247448d402a656e00", inventory)
        self.assertIn('expected_os_id: "nura"', inventory)
        self.assertIn('expected_kernel_release: "7.0.1-postmarketos-grate-dmavde1-minus-cma"', inventory)
        self.assertIn("nuraloumi_approved_git_sha:", inventory)
        self.assertIn("nuraloumi_approved_tar_sha256:", inventory)
        self.assertIn("nuraloumi_approved_manifest_sha256:", inventory)
        self.assertIn("nura_ci_sha == nuraloumi_approved_git_sha", book)
        self.assertIn("('EMMC_CID=' ~ expected_emmc_cid)", book)
        self.assertIn("('ROOT=' ~ expected_root_source)", book)
        self.assertIn("('OS_ID=' ~ expected_os_id)", book)
        self.assertIn("'MUSL_LOADER=present'", book)
        self.assertIn("playbook_dir }}/../data/nuraloumi/", book)
        self.assertNotIn("/workspace/deploy/ansible/tools/nuraloumi_ci_payload.py", book)
        self.assertIn("SL101_NURALOUMI_STAGE", entry)
        self.assertIn("SL101_APPLY", entry)
        tasks = (DEPLOY / "playbooks/nuraloumi-stage-tasks.yml").read_text()
        self.assertGreaterEqual(tasks.count("when: not ansible_check_mode"), 8)
        for forbidden in ("sl101-100", "reboot ", "kexec ", "dd if=", "fw_setenv",
                          "systemctl restart", "rc-service restart"):
            self.assertNotIn(forbidden, book)
        r = subprocess.run(["ansible-playbook", "-i", str(DEPLOY / "inventory/hosts.yml"),
                            str(DEPLOY / "playbooks/nuraloumi-stage.yml"),
                            "--syntax-check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--fixture":
        make_fixture(Path(sys.argv[2]))
    else:
        unittest.main()
