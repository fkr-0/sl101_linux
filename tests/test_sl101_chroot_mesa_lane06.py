"""Lane 06: isolated, zero-fuzz Mesa patch and manifest checks (no device I/O)."""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches/mesa-25.0.7"
BASE = ROOT / "build/mesa-grate-clean/mesa-25.0.7.tar.xz"
PRODUCTION = ROOT / "work/sl101-grate-production-20261004/grate-src"


class ChrootMesaLane06Tests(unittest.TestCase):
    def test_series_hashes_and_0035_0036_membership(self):
        rows = []
        for line in (PATCHES / "series").read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            digest, filename = line.split()
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertEqual(filename, pathlib.PurePath(filename).name)
            self.assertEqual(hashlib.sha256((PATCHES / filename).read_bytes()).hexdigest(), digest)
            rows.append(filename)
        self.assertEqual(len(rows), len(set(rows)))
        for name in ("0035-dri-expose-stencil-only-visuals.patch",
                     "0036-grate-vp-split-uniform-fetches-and-null-shader-draw-guard.patch"):
            self.assertIn(name, rows)

    def _patch(self, name: str, files: dict[str, pathlib.Path | None]):
        if not shutil.which("patch"):
            self.skipTest("GNU patch not installed")
        with tempfile.TemporaryDirectory(prefix="sl101-lane06-patch-") as tmp:
            root = pathlib.Path(tmp)
            for rel, src in files.items():
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src is None:
                    with tarfile.open(BASE, mode="r:xz") as archive:
                        member = archive.extractfile("mesa-25.0.7/" + rel)
                        self.assertIsNotNone(member)
                        dest.write_bytes(member.read())
                else:
                    shutil.copyfile(src, dest)
            payload = (PATCHES / name).read_bytes()
            for dry_run in (True, False):
                args = ["patch", "--batch", "--fuzz=0", "--no-backup-if-mismatch", "-p1"]
                if dry_run:
                    args.insert(1, "--dry-run")
                completed = subprocess.run(args, input=payload, cwd=root,
                                           capture_output=True, timeout=15)
                self.assertEqual(completed.returncode, 0,
                                 completed.stdout.decode(errors="replace")
                                 + completed.stderr.decode(errors="replace"))
                self.assertFalse(list(root.rglob("*.rej")))
                self.assertFalse(list(root.rglob("*.orig")))

    def test_patch_0035_from_pristine_mesa(self):
        self._patch("0035-dri-expose-stencil-only-visuals.patch", {
            "src/gallium/frontends/dri/dri_screen.c": None,
        })

    def test_patch_0036_from_pinned_production_grate(self):
        self._patch("0036-grate-vp-split-uniform-fetches-and-null-shader-draw-guard.patch", {
            "src/gallium/drivers/grate/grate_draw.c": PRODUCTION / "grate_draw.c",
            "src/gallium/drivers/grate/vp/tgsi.c": PRODUCTION / "vp/tgsi.c",
            "src/gallium/drivers/grate/grate_compiler.h": PRODUCTION / "grate_compiler.h",
        })

    def test_complete_candidate_series_applies_in_order_without_fuzz(self):
        """Fail closed if a candidate series entry no longer applies to pinned inputs."""
        if not shutil.which("patch"):
            self.skipTest("GNU patch not installed")
        rows = []
        for line in (PATCHES / "series").read_text().splitlines():
            if line and not line.startswith("#"):
                _, filename = line.split()
                rows.append(filename)
        paths = set()
        for filename in rows:
            for line in (PATCHES / filename).read_text().splitlines():
                if line.startswith("--- a/"):
                    paths.add(line[len("--- a/"):])
        with tempfile.TemporaryDirectory(prefix="sl101-lane06-full-series-") as tmp:
            root = pathlib.Path(tmp)
            mesa_paths = []
            for rel in sorted(paths):
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                grate_prefix = "src/gallium/drivers/grate/"
                if rel.startswith(grate_prefix):
                    shutil.copyfile(PRODUCTION / rel[len(grate_prefix):], dest)
                else:
                    mesa_paths.append(rel)
            with tarfile.open(BASE, mode="r:xz") as archive:
                for rel in mesa_paths:
                    member = archive.extractfile("mesa-25.0.7/" + rel)
                    self.assertIsNotNone(member)
                    (root / rel).write_bytes(member.read())
            for filename in rows:
                completed = subprocess.run(
                    ["patch", "--batch", "--fuzz=0", "--no-backup-if-mismatch", "-p1"],
                    input=(PATCHES / filename).read_bytes(),
                    cwd=root, capture_output=True, timeout=20,
                )
                self.assertEqual(completed.returncode, 0, filename + "\n"
                                 + completed.stdout.decode(errors="replace")
                                 + completed.stderr.decode(errors="replace"))
            self.assertFalse(list(root.rglob("*.rej")))
            self.assertFalse(list(root.rglob("*.orig")))

    def test_apply_rejected_before_any_ssh_or_file_access(self):
        """Untrusted handoff text cannot confer authorization, even with --apply."""
        script = ROOT / "scripts/sl101-chroot-mesa-deploy.sh"
        with tempfile.TemporaryDirectory(prefix="sl101-lane06-deny-") as tmp:
            root = pathlib.Path(tmp)
            sentinel = root / "ssh-called"
            fake_ssh = root / "ssh"
            fake_ssh.write_text("#!/bin/sh\ntouch '" + str(sentinel) + "'\nexit 0\n")
            fake_ssh.chmod(0o755)
            handoff = root / "handoff"
            handoff.write_text("SL101-LINUX-01-PROMPT-KMS-ATOMIC-EINVAL-20261103-324D9D\nlane 06\nhandoff approved\n")
            import os
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ.get("PATH", ""))
            result = subprocess.run(["bash", str(script), "--apply", "--handoff-file",
                                     str(handoff), "--manifest", str(root / "missing"),
                                     "--expected-cid", "a" * 32],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("--apply disabled", result.stderr)
            self.assertFalse(sentinel.exists(), "apply attempted remote operation")

    def test_deployer_executable_and_no_apply_gate(self):
        script = ROOT / "scripts/sl101-chroot-mesa-deploy.sh"
        self.assertTrue(script.stat().st_mode & 0o111, "deploy script must remain executable")
        result = subprocess.run([str(script), "--apply"], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("--apply disabled", result.stderr)

    def test_build_is_offline_and_bounded(self):
        recipe = (ROOT / "build/mesa-grate-clean/build.sh").read_text()
        self.assertIn("--wrap-mode=nodownload", recipe)
        self.assertIn("refusing network download", recipe)
        self.assertNotIn("wget ", recipe)
        self.assertNotIn("-j$(nproc)", recipe)
        self.assertIn("ninja -C builddir -j2", recipe)

    def test_shell_syntax(self):
        for file, shell in (
            (ROOT / "build/mesa-grate-clean/build.sh", "sh"),
            (ROOT / "scripts/sl101-chroot-mesa-deploy.sh", "bash"),
        ):
            completed = subprocess.run([shell, "-n", str(file)], capture_output=True)
            self.assertEqual(completed.returncode, 0,
                             completed.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
