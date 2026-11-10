"""Offline cross-lane wiring guards; never treated as a WebKit build.

These checks are intentionally independent from the component-local stubs.
The dynamic B+C Unix-socket integration runs in run-crosslane-host.sh.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class IntegrationContractTests(unittest.TestCase):
    def text(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_explicit_sources_and_dependency_gate(self):
        meson = self.text("meson.build")
        sources = (
            "src/engine/main.c",
            "src/engine/engine.c",
            "src/engine/options.c",
            "src/navigation/navigation.c",
            "src/navigation/state.c",
            "src/navigation/url.c",
            "src/control/control.c",
        )
        for source in sources:
            with self.subTest(source=source):
                self.assertIn("'" + source + "'", meson)
                self.assertTrue((ROOT / source).is_file())
        self.assertNotIn("glob(", meson)
        for dep in ("wpe-webkit-2.0", "wpe-platform-2.0", "json-glib-1.0", "gio-unix-2.0"):
            self.assertRegex(meson, rf"dependency\('{re.escape(dep)}'.*required: true\)")
        self.assertNotRegex(meson, r"(?m)^\+")
        for name in (
            "engine-options-host",
            "navigation-host",
            "control-ipc-host",
            "navigation-control-integration-host",
        ):
            self.assertIn("'" + name + "'", meson)

    def test_actual_engine_uses_control_and_navigation_in_order(self):
        engine = self.text("src/engine/engine.c")
        self.assertIn('#include <wpe/wpe-platform.h>', engine)
        startup = engine.index("nurabrowser_nav_attach(&engine.context);")
        control = engine.index("nurabrowser_control_start(&engine.context, socket_path, &error)")
        self.assertLess(startup, control)
        stop = engine.index("nurabrowser_control_stop(&engine->context)")
        detach = engine.index("nurabrowser_nav_shutdown(&engine->context)")
        self.assertLess(stop, detach)
        self.assertIn('g_build_filename(dir, "nura-browser.sock", NULL)', engine)

    def test_control_actual_runtime_path_matches_host_integration(self):
        engine = self.text("src/engine/engine.c")
        integration = self.text("tests/test_crosslane_ipc.c")
        self.assertIn('"nura-browser.sock"', engine)
        self.assertIn('"nura-browser.sock"', integration)
        self.assertIn("nurabrowser_control_start(&f->ctx, f->socket_path", integration)

    def test_no_public_alias_and_no_sandbox_disable(self):
        meson = self.text("meson.build")
        launcher = self.text("scripts/launch.sh")
        self.assertIn("rename: ',browse'", meson)
        self.assertNotIn("sl101-browse", launcher)
        self.assertIn("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS", launcher)
        self.assertIn("bubblewrap missing", launcher)
        self.assertIn("xdg-dbus-proxy missing", launcher)
        self.assertNotRegex(launcher, r"(?m)^\s*(?:eval|source)\s+")


if __name__ == "__main__":
    unittest.main()
