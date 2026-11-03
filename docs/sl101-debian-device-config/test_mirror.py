import unittest
from pathlib import Path
import hashlib
import os
import json
import subprocess
import shutil
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "sl101-device-config"

class MirrorTests(unittest.TestCase):
    def test_full_source_coverage(self):
        entries = json.loads((ROOT / "source-parity.json").read_text())
        actual = {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file() or p.is_symlink()}
        self.assertEqual(actual, {e["source"] for e in entries})
        for entry in entries:
            self.assertEqual(hashlib.sha256((SOURCE / entry["source"]).read_bytes()).hexdigest(), entry["sha256"])
            self.assertIn(entry["decision"], {"copied", "adapted", "replaced", "not-applicable"})
    def test_manifest_hashes(self):
        entries = json.loads((ROOT / "files-manifest.json").read_text())
        self.assertEqual(len(entries), len({e["path"] for e in entries}))
        for entry in entries:
            path = ROOT / entry["path"].lstrip("/")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
    def test_shell_and_xml(self):
        ET.parse(ROOT / "home/user/.config/labwc/rc.xml")
        for path in (ROOT / "usr/local/bin").iterdir():
            if path.is_file():
                subprocess.run(["sh", "-n", str(path)], check=True)
        subprocess.run(["sh", "-n", str(ROOT / "usr/local/libexec/sl101-alsa-companding")], check=True)
    def test_stage_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'target'
            target.mkdir()
            (target / '.sl101-debian-staging').touch()
            backup = Path(tmp) / 'backup'
            base = ['python3', str(ROOT / 'install.py')]
            subprocess.run(base + ['install', '--target-root', str(target), '--backup', str(backup), '--apply'], check=True, capture_output=True)
            self.assertTrue((target / 'usr/local/bin/sl101-desktop').is_file())
            if shutil.which('systemd-analyze'):
                unitdir = target / 'usr/lib/systemd/system'
                unitdir.mkdir(parents=True, exist_ok=True)
                (unitdir / 'sysinit.target').write_text('[Unit]\nDescription=Stub test target\n')
                verify = subprocess.run(['systemd-analyze', 'verify', '--root='+str(target), 'sl101-alsa-companding.service'], capture_output=True, text=True)
                self.assertEqual(verify.returncode, 0, verify.stderr)
                user_unit = (target / 'etc/systemd/user/sl101-desktop.service').read_text()
                self.assertIn('ExecStart=/usr/local/bin/sl101-desktop', user_unit)
                self.assertNotIn('[Install]', user_unit)
            subprocess.run(base + ['rollback', '--target-root', str(target), '--backup', str(backup), '--apply'], check=True, capture_output=True)
            self.assertFalse((target / 'usr/local/bin/sl101-desktop').exists())

    def test_rollback_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'root'
            prior = target / 'usr/local/bin/sl101-desktop'
            prior.parent.mkdir(parents=True)
            (target / '.sl101-debian-staging').touch()
            prior.write_text('previous-version\n')
            prior.chmod(0o700)
            backup = Path(tmp) / 'backups'
            common = ['python3', str(ROOT / 'install.py')]
            args = ['--target-root', str(target), '--backup', str(backup), '--apply']
            subprocess.run(common + ['install'] + args, check=True, capture_output=True)
            subprocess.run(common + ['rollback'] + args, check=True, capture_output=True)
            self.assertEqual(prior.read_text(), 'previous-version\n')
            self.assertEqual(prior.stat().st_mode & 0o777, 0o700)

    def test_reject_destination_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'target'
            target.mkdir()
            (target / '.sl101-debian-staging').touch()
            outside = root / 'outside'
            outside.mkdir()
            (target / 'etc').symlink_to(outside, target_is_directory=True)
            proc = subprocess.run(['python3', str(ROOT / 'install.py'), 'install', '--target-root', str(target), '--backup', str(root / 'backup'), '--apply'], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse((root / 'backup').exists())
            self.assertEqual(list(outside.iterdir()), [])

    def test_apply_requires_explicit_staging_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'target'
            target.mkdir()
            backup = Path(tmp) / 'backup'
            command = ['python3', str(ROOT / 'install.py'), 'install', '--target-root', str(target), '--backup', str(backup), '--apply']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('staging root', result.stderr)
            self.assertFalse(backup.exists())

    def test_stage_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['python3', str(ROOT / 'install.py'), 'install', '--target-root', tmp], check=True, capture_output=True)
            self.assertEqual(list(root.iterdir()), [])

    def test_staging_help(self):
        subprocess.run(['python3', str(ROOT / 'install.py'), '--help'], check=True, capture_output=True)

    def test_keymap_and_shortcuts(self):
        root = ET.parse(ROOT / "home/user/.config/labwc/rc.xml").getroot()
        keys = {node.get("key") for node in root.findall("./keyboard/keybind")}
        for shortcut in ["W-Return", "W-d", "W-e", "W-b", "W-u", "W-S-r", "C-A-F1", "C-A-F7"]:
            self.assertIn(shortcut, keys)
        self.assertEqual((ROOT / "home/user/.config/labwc/environment").read_text().strip(), "XKB_DEFAULT_LAYOUT=de")
        keyd = (ROOT / "etc/keyd/sl101.conf").read_text()
        for number in range(1, 8):
            self.assertIn(f"{number} = C-A-f{number}", keyd)
        sway = (ROOT / "home/user/.config/sway/config").read_text()
        self.assertIn("xkb_layout de", sway)
        self.assertIn("Ctrl+Mod1+F7", sway)

    def test_no_session_without_logind_runtime(self):
        env = dict(os.environ)
        env.pop("XDG_RUNTIME_DIR", None)
        r = subprocess.run(["sh", str(ROOT / "usr/local/bin/sl101-desktop")], env=env, capture_output=True)
        self.assertNotEqual(r.returncode, 0)

    def test_renderer_recovery(self):
        desktop = (ROOT / "usr/local/bin/sl101-desktop").read_text()
        self.assertIn("WLR_RENDERER=pixman", desktop)
        self.assertNotIn("/opt/", desktop)
        self.assertNotIn("/run/sl101-desktop-user", desktop)
