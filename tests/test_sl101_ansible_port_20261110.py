"""Offline tests for executable cutover and VDE-inclusive kernel release gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AN = ROOT / 'deploy/ansible'
sys.path.insert(0, str(AN / 'tools'))
from render_public import canonical, render  # noqa E402
from verify_kernel import verify  # noqa E402


class Sl101AnsiblePortTests(unittest.TestCase):
    def test_inventory_reconciles_distinct_debian_and_nura_media(self):
        inventory = (AN / 'inventory/hosts.yml').read_text()
        self.assertIn('03534453553332478030be3f6400b900', inventory)
        self.assertIn('035344534c31323880ac79a543010300', inventory)
        self.assertIn('sltwrpbootdebian', inventory)
        self.assertIn('sl101-nura', inventory)

    def test_exact_comma_namespace_and_no_other_public_names(self):
        self.assertEqual(canonical('sl101-cog-wpe'), ',cog-wpe')
        self.assertEqual(canonical('sl101-desktop'), ',desktop')
        for invalid in ('cog', '../sl101-x', 'sl101-X', 'sl101-a.sh'):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    canonical(invalid)

    def test_render_both_architectures_without_alias_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            for profile, expected in [('nura', 24), ('debian', 15)]:
                with self.subTest(profile=profile):
                    target = Path(td) / profile
                    result = render(profile, ROOT, target)
                    self.assertEqual(len(result['commands']), expected)
                    self.assertEqual(len(set(result['commands'])), expected)
                    self.assertTrue((target / 'bin/,browse').exists())
                    sway = (target / 'config/home/user/.config/sway/config').read_text()
                    self.assertIn('/usr/local/bin/,foot-launch', sway)
                    self.assertNotIn('/usr/local/bin/sl101-foot-launch', sway)
                    desktop = (target / 'config/usr/share/applications/sl101-browse.desktop').read_text()
                    self.assertIn('Exec=/usr/local/bin/,browse', desktop)
                    epiphany = (target / 'config/usr/share/applications/sl101-epiphany.desktop').read_text()
                    self.assertIn('Exec=/usr/local/bin/,epiphany', epiphany)
                    self.assertFalse(any(x.name.startswith('sl101-') for x in (target / 'bin').iterdir()))
                    self.assertFalse((AN / 'aliases.yml').exists())
                    if profile == 'nura':
                        kms = (target / 'bin/,kms-run').read_text()
                        cog = (target / 'bin/,cog-wpe-root').read_text()
                        panel = (target / 'bin/,sway-panel').read_text()
                        self.assertIn('rc-service sl101-desktop stop', kms)
                        self.assertNotIn('rc-service ,desktop', kms)
                        self.assertIn('/run/sl101-desktop.pid', cog)
                        self.assertNotIn('/run/,desktop.pid', cog)
                        self.assertIn('sl101-sway-panel.lock', panel)
                        init = (target / 'config/etc/init.d/sl101-desktop').read_text()
                        self.assertIn('command="/usr/local/bin/,desktop"', init)
                        self.assertIn('pidfile="/run/sl101-desktop.pid"', init)

    def test_fresh_kernel_without_modules_or_vde_never_passes(self):
        with tempfile.TemporaryDirectory() as td:
            errors = verify(Path(td), '7.0.1-postmarketos-grate-dmafix1')
            self.assertTrue(any('zImage' in e for e in errors))
            self.assertTrue(any('module' in e for e in errors))
            self.assertTrue(any('tegra-vde' in e for e in errors))

    def test_known_dmafix1_blocks_until_vde_patch_included(self):
        candidate = ROOT / 'work/sl101-prod-dma-init-20261110'
        if not candidate.joinpath('out/arch/arm/boot/zImage').is_file():
            self.skipTest('host-only dmafix1 build not on this checkout')
        errors = verify(candidate, '7.0.1-postmarketos-grate-dmafix1')
        self.assertIn('VDE cached_capture parameter ABSENT (VDE v2 patch missing)', errors)

    def test_site_protects_live_desktops_and_requires_explicit_gates(self):
        book = (AN / 'playbooks/site.yml').read_text()
        entrypoint = (AN / 'entrypoint.sh').read_text()
        for name in ('sway', 'sl101-sway', 'labwc'):
            self.assertIn(name, book)
        self.assertIn('SL101_CUTOVER', book)
        for name in ('SL101_APPLY', 'check', 'apply', 'test'):
            self.assertIn(name, entrypoint)
        self.assertIn('when: (sl101_cutover | bool) and not ansible_check_mode', book)

    def test_python_and_shell_syntax(self):
        r = subprocess.run(['sh', '-n', str(AN / 'entrypoint.sh')], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        result = subprocess.run(['python3', '-m', 'py_compile',
                                str(AN / 'tools/render_public.py'),
                                str(AN / 'tools/verify_kernel.py')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
