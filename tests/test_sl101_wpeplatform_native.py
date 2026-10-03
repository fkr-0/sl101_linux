import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUALIFY = ROOT / "scripts/sl101-wpeplatform-host-qualify.py"
LAUNCH = ROOT / "scripts/sl101-wpeplatform-launch.sh"
DOC = ROOT / "docs/sl101-wpeplatform-native-20261003.md"


class WPEPlatformNativeTests(unittest.TestCase):
    @unittest.skipUnless(
        (ROOT / "work/sl101-wpe-armhf-build-qualification-20261003/wpe-audit/package-control.txt").exists(),
        "hardware/build qualification requires the separately archived WPE evidence bundle",
    )
    def test_offline_host_qualification_passes_archived_evidence(self):
        result = subprocess.run(
            [sys.executable, str(QUALIFY)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["pass"])
        self.assertEqual(payload["engine"]["version"], "2.54.0-2")
        self.assertEqual(payload["engine"]["architecture"], "armhf")
        self.assertTrue(payload["engine"]["sha256_matches"])
        self.assertEqual(payload["cpu_audit"]["unexpected_failure_paths"], [])
        self.assertTrue(payload["cpu_audit"]["gst_ptp_helper_must_be_excluded"])
        self.assertTrue(all(payload["wpeplatform_symbols"].values()))
        self.assertTrue(all(payload["runtime_dependencies"].values()))

    def test_launcher_is_native_and_software_first(self):
        text = LAUNCH.read_text(encoding="utf-8")
        self.assertIn("wpe-webkit-2.0/MiniBrowser", text)
        self.assertNotIn("/usr/bin/cog", text)
        self.assertIn("RENDERER=${SL101_WPE_RENDERER:-software}", text)
        self.assertIn("GALLIUM_DRIVER=softpipe", text)
        self.assertIn("MESA_LOADER_DRIVER_OVERRIDE=swrast", text)
        self.assertIn("MESA_LOADER_DRIVER_OVERRIDE=grate", text)
        self.assertIn("/opt/grate-glibc", text)

    def test_launcher_preserves_sandbox_and_has_no_deployment_actions(self):
        text = LAUNCH.read_text(encoding="utf-8")
        self.assertIn("command -v bwrap", text)
        self.assertIn("command -v xdg-dbus-proxy", text)
        self.assertIn("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS", text)
        lowered = text.lower()
        for forbidden in ("--no-sandbox", "ssh ", "scp ", "mount ", "chroot ", "reboot ", "kexec ", "dd if="):
            self.assertNotIn(forbidden, lowered)

    def test_skia_webgl_and_buffer_sharing_are_not_conflated(self):
        launch = LAUNCH.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")
        self.assertIn("SL101_WPE_SKIA_COMPOSITION", launch)
        self.assertIn("GBM / DMA-BUF", doc)
        self.assertIn("WebGL", doc)
        self.assertIn("Skia", doc)
        self.assertIn("separate gate", doc)

    def test_document_records_offline_custom_c_header_gap(self):
        doc = DOC.read_text(encoding="utf-8")
        self.assertIn("development-header gap", doc)
        self.assertIn("libwpewebkit-2.0-1", doc)
        self.assertIn("MiniBrowser", doc)
        self.assertIn("2.54.0-2", doc)


if __name__ == "__main__":
    unittest.main()
