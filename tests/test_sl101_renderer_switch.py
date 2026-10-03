"""Offline service simulation: never starts/stops the real desktop."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import fcntl
spec = importlib.util.spec_from_file_location('switch', Path(__file__).parents[1] / 'scripts/sl101-renderer-switch.py')
switch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(switch)

class Fake:
    def __init__(self, fails=None): self.events = []; self.fails = fails
    def command(self, service, operation): self.events.append((service, operation))
    def select(self, mode): self.events.append(('select', mode))
    def ready(self, mode): return mode != self.fails

class SwitchTests(unittest.TestCase):
    def test_qualification_lock_refuses_second_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'qualification.lock'
            with path.open('a') as owner:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, 'qualification owns'):
                    switch.acquire_lock(path)
            with switch.acquire_lock(path):
                pass
    def test_success_is_runtime_only(self):
        fake = Fake(); switch.change('grate', fake)
        self.assertEqual([v for k, v in fake.events if k == 'select'], ['grate'])
        self.assertEqual(fake.events[-1], ('sl101-wayvnc', 'start'))
    def test_grate_failure_recovers_pixman(self):
        fake = Fake('grate'); switch.change('grate', fake)
        self.assertEqual([v for k, v in fake.events if k == 'select'], ['grate', 'pixman'])
    def test_pixman_failure_is_reported(self):
        with self.assertRaises(RuntimeError): switch.change('pixman', Fake('pixman'))
    def test_invalid_mode_has_no_service_effects(self):
        fake = Fake()
        with self.assertRaises(ValueError): switch.change("anything", fake)
        self.assertEqual(fake.events, [])
    def test_candidate_is_exactly_pinned(self):
        self.assertEqual(switch.HASHES['lib/libgallium-25.0.7.so'], switch.PREFIX.name.removeprefix('sl101-grate-'))
        self.assertEqual(switch.OVERRIDE.parent, Path('/run'))
