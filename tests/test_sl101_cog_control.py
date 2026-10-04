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
