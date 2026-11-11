"""Host-only safety gates for the native WPE headless CI lifecycle."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HeadlessLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "src/engine/engine.c").read_text()

    def test_cannot_pass_without_load_finished(self):
        src = self.source
        self.assertIn("engine->load_finished = TRUE;", src)
        self.assertIn("engine->load_failed = TRUE;", src)
        self.assertIn("if (!engine->load_finished || engine->load_failed)", src)
        self.assertIn("request_stop(engine, EXIT_FAILURE);", src)
        self.assertIn("headless CI PASS", src)

    def test_loaded_state_is_connected_to_real_webkit_signals(self):
        src = self.source
        self.assertRegex(src, r'void\s+on_load_changed\s*\(\s*WebKitWebView')
        self.assertIn("stage == WEBKIT_LOAD_FINISHED", src)
        self.assertIn('"load-changed",', src)
        self.assertIn("G_CALLBACK(on_load_changed)", src)
        self.assertIn('"load-failed",', src)
        self.assertIn("G_CALLBACK(on_load_failed)", src)
        self.assertIn("require_load_completion = options->exit_after_ms != 0;", src)

    def test_early_shutdown_not_a_success(self):
        src = self.source
        for event in ("on_sigint", "on_sigterm", "on_wpe_closed"):
            body = re.search(
                rf"\b{event}\s*\([^)]*\)\s*\{{(.*?)\n\}}", src, re.DOTALL
            )
            self.assertIsNotNone(body, event)
            self.assertIn("require_load_completion ? EXIT_FAILURE", body.group(1))
        self.assertNotIn("engine.stopping ? engine.result : EXIT_SUCCESS", src)


if __name__ == "__main__":
    unittest.main()
