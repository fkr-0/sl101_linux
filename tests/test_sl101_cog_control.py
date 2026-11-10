import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('control', Path(__file__).parents[1] / 'scripts/sl101-cog-control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class CogControlTests(unittest.TestCase):
    def test_domain_and_query(self):
        self.assertEqual(control.normalize_url(' de.wikipedia.org '), 'https://de.wikipedia.org')
        self.assertEqual(control.normalize_url('https://example.org/?q=a&b=2'), 'https://example.org/?q=a&b=2')

    def test_rejects_local_script_credentials_and_controls(self):
        for url in ['file:///etc/passwd', 'javascript://alert(1)', 'https://a:b@example.org', '', 'https://example.org/\ncmd']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                control.normalize_url(url)

    def test_private_bus_extraction(self):
        self.assertEqual(control.browser_bus(b'A=1\0DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/dbus-test,guid=abc\0'),
                         'unix:path=/tmp/dbus-test,guid=abc')
        with self.assertRaises(ValueError):
            control.browser_bus(b'DBUS_SESSION_BUS_ADDRESS=tcp:host=example.org\0')


class CogControlTransparencyTests(unittest.TestCase):
    TEXT = (Path(__file__).parents[1] / 'scripts/sl101-cog-control.py').read_text()

    def test_no_kernel_release_pin_anywhere(self):
        self.assertNotIn('7.0.1-postmarketos-grate', self.TEXT)
        self.assertNotIn('os.uname().release !=', self.TEXT)
        self.assertNotIn('Tablet identity mismatch', self.TEXT)

    def test_hardware_check_names_expected_and_found(self):
        with self.assertRaises((ValueError, OSError)) as caught:
            control.check_hardware()
        if isinstance(caught.exception, ValueError):
            message = str(caught.exception)
            self.assertIn("expected 'sl101-nura'", message)
            self.assertIn('hostname is', message)

    def _report(self, status, comm, env, mode):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'status'
            if status is not None:
                path.write_text(status)
            old = (control.RENDER_STATUS, control.compositor_env)
            control.RENDER_STATUS = path
            control.compositor_env = lambda: (comm, env)
            try:
                return control.render_report(mode)
            finally:
                control.RENDER_STATUS, control.compositor_env = old

    def test_report_says_pixman_and_why_grate_was_not_used(self):
        report = self._report('compositor=sway\nrequested=grate\nreason=FALLBACK to PIXMAN: Grate bundle check failed: hash\n',
                              'sl101-sway', {'WLR_RENDERER': 'pixman'}, 'software')
        self.assertIn('PIXMAN (software, CPU)', report)
        self.assertIn('grate was requested but is NOT used', report)
        self.assertIn('Grate bundle check failed: hash', report)
        self.assertIn('Cog software mode', report)
        self.assertIn('no EGL', report)

    def test_report_says_gpu_when_gles2(self):
        report = self._report('compositor=sway\nrequested=grate\n', 'sl101-sway', {'WLR_RENDERER': 'gles2'}, 'gpu')
        self.assertIn('GLES2/EGL via Grate (GPU)', report)
        self.assertNotIn('NOT used', report)
        self.assertIn('Cog GPU mode', report)

    def test_report_without_status_file_or_compositor_is_honest(self):
        self.assertIn('no /run/sl101-render-status', self._report(None, 'labwc', {'WLR_RENDERER': 'pixman'}, 'software'))
        self.assertIn('no compositor process found', self._report(None, None, {}, 'software'))
        self.assertIn("kernel  : ", self._report(None, None, {}, 'software'))
        self.assertIn('not checked', self._report(None, None, {}, 'software'))

    def test_self_path_is_used_for_reexec(self):
        self.assertEqual(control.SELF, str(Path(control.__file__).resolve()))
        self.assertIn("subprocess.Popen([SELF, action, url]", self.TEXT)
        self.assertIn("'sudo', '-n', SELF", self.TEXT)
