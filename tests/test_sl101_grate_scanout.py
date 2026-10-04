import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('scanout', Path(__file__).parents[1] / 'scripts/sl101-grate-scanout-build.py')
scanout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanout)

class ScanoutTests(unittest.TestCase):
    def test_scanout_only_keeps_other_flags(self):
        source = 'flags = DRM_TEGRA_GEM_CREATE_BOTTOM_UP;\nflags = DRM_TEGRA_GEM_CREATE_BOTTOM_UP;\n   if (template->target != PIPE_BUFFER) {\n'
        patched = scanout.correct_scanout_flags(source)
        self.assertIn('if (template->bind & PIPE_BIND_SCANOUT)\n      flags &= ~DRM_TEGRA_GEM_CREATE_BOTTOM_UP;', patched)
        self.assertEqual(patched.count('flags = DRM_TEGRA_GEM_CREATE_BOTTOM_UP;'), 2)
        self.assertTrue(patched.endswith('   if (template->target != PIPE_BUFFER) {\n'))
    def test_source_drift_fails_closed(self):
        with self.assertRaises(ValueError): scanout.correct_scanout_flags('different source')
