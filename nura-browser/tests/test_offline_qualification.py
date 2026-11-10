"""Host-only regression suite for build, sandbox, renderer, and ARMHF gates."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/launch.sh"
QUALIFY = ROOT / "scripts/qualify.py"
BUILD = ROOT / "scripts/build-armhf.sh"
MANIFEST = ROOT / "packaging/create-manifest.py"

spec = importlib.util.spec_from_file_location("nurabrowser_qualify", QUALIFY)
assert spec and spec.loader
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


class BuildContractTests(unittest.TestCase):
    def test_explicit_source_inventory(self):
        text = (ROOT / "meson.build").read_text(encoding="utf-8")
        for path in ("src/engine/main.c", "src/engine/engine.c",
                     "src/engine/options.c", "src/navigation/navigation.c",
                     "src/navigation/state.c", "src/navigation/url.c",
                     "src/control/control.c"):
            self.assertIn(f"'{path}'", text)
        self.assertNotIn("glob(", text)
        self.assertIn("c_std=c11", text)

    def test_explicit_pkg_config_linkage(self):
        text = (ROOT / "meson.build").read_text(encoding="utf-8")
        for dep in q.DEPS:
            self.assertIn(f"dependency('{dep}'", text)
        self.assertIn("version: '>=2.54.0'", text)
        self.assertIn("rename: ',browse'", text)
        self.assertNotIn("sl101-browse", text.replace("No sl101-browse compatibility shim.", ""))

    def test_no_legacy_api_in_code(self):
        self.assertEqual(q.source_gate(ROOT), [])

    def test_cross_toolchain_flags(self):
        text = (ROOT / "packaging/armhf-gnueabihf.ini").read_text(encoding="utf-8")
        for flag in ("-march=armv7-a", "-mfpu=vfpv3-d16",
                     "-mfloat-abi=hard", "-fno-tree-vectorize"):
            self.assertIn(flag, text)
        self.assertNotIn("-mfpu=neon", text)
        self.assertIn("arm-linux-gnueabihf-gcc", text)
        self.assertIn("armhf_qualification", (ROOT / "meson.build").read_text())

    def test_native_header_absence_is_reported_not_faked(self):
        run = subprocess.run(["python3", str(QUALIFY), "--mode", "host"],
                             text=True, capture_output=True, check=False)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["pass"], run.returncode == 0)
        self.assertEqual(payload["readiness"]["on_device"], "not-tested")
        self.assertEqual(payload["schema"], "sl101.nurabrowser.build-qualification.v1")
        for header in q.HEADERS:
            if payload["checks"]["dependencies"]["headers"][header] is None:
                self.assertIn(f"missing development header: <{header}>", payload["errors"])

    def test_cross_missing_sysroot_is_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "not-present"
            payload = q.qualify("armhf", missing, [])
            self.assertFalse(payload["pass"])
            self.assertIn("missing prepared ARMHF glibc sysroot: --sysroot", payload["errors"])

    def test_status_version_and_architecture_parser(self):
        status = ("Package: libwpewebkit-2.0-1\n"
                  "Status: install ok installed\n"
                  "Version: 2.54.0-2\nArchitecture: armhf\n\n"
                  "Package: another\nVersion: 1.0\n")
        parsed = q.parse_status(status)
        self.assertEqual(parsed["libwpewebkit-2.0-1"]["Version"], "2.54.0-2")
        self.assertEqual(parsed["libwpewebkit-2.0-1"]["Architecture"], "armhf")

    def test_host_elf_rejected_as_non_armhf(self):
        candidate = Path(shutil.which("python3") or "/bin/sh")
        errors = q.audit_elf(candidate)
        self.assertTrue(errors, "Native host ELF must not be marked armhf-qualified")

    def test_armhf_elf_disassembly_rejects_neon_and_high_vfp(self):
        """Mock only readelf/objdump output; never fake a compiled ARM binary."""
        def run_case(instruction):
            def fake_run(*argv, env=None):
                if "-h" in argv:
                    out = "Machine: ARM\nFlags: 0x5000400, Version5 EABI, hard-float ABI\n"
                elif "-A" in argv:
                    out = "Tag_CPU_arch: v7\nTag_FP_arch: VFPv3-D16\n"
                else:
                    out = "  100: e1a00000    " + instruction + "\n"
                return subprocess.CompletedProcess(argv, 0, out, "")
            with tempfile.TemporaryDirectory() as temp:
                elf = Path(temp) / "candidate"
                elf.write_bytes(b"\x7fELF")
                with patch.object(q, "run", side_effect=fake_run), \
                     patch.object(q.shutil, "which", return_value="/usr/bin/verified"):
                    return q.audit_elf(elf)
        self.assertEqual(run_case("vmov.f64 d0, d1"), [])
        self.assertTrue(any("NEON" in e for e in run_case("vld1.8 {d0}, [r0]")))
        self.assertTrue(any("NEON" in e for e in run_case("vadd.f32 d16, d1, d2")))

    def test_manifest_refuses_native_elf(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "release.json"
            bin_dir = Path(temp) / "build"
            bin_dir.mkdir()
            shutil.copy2(shutil.which("python3"), bin_dir / "nurabrowser-core")
            result = subprocess.run(["python3", str(MANIFEST),
                                     "--build-dir", str(bin_dir),
                                     "--output", str(out)],
                                    text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing package manifest", result.stderr)
            self.assertFalse(out.exists())

    def test_missing_legacy_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / "src/test"
            src.mkdir(parents=True)
            (src / "bad.c").write_text("#include <wpebackend-fdo/foo.h>\n", encoding="utf-8")
            self.assertTrue(q.source_gate(Path(temp)))


class LauncherTests(unittest.TestCase):
    def shell(self, *args: str, env: dict[str, str] | None = None):
        clean = dict(os.environ)
        for key in ("NURABROWSER_PRIVATE_ROOT", "NURABROWSER_EXPECTED_STATUS_SHA256",
                    "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS",
                    "WEBKIT_USE_SANDBOX", "NURABROWSER_ALLOW_DRM"):
            clean.pop(key, None)
        if env:
            clean.update(env)
        return subprocess.run(["sh", str(SCRIPT), *args],
                              text=True, capture_output=True, check=False, env=clean)

    def test_shell_syntax(self):
        for script in (SCRIPT, BUILD):
            p = subprocess.run(["sh", "-n", str(script)], check=False)
            self.assertEqual(p.returncode, 0, script)

    def test_help_is_side_effect_free(self):
        p = self.shell("--help")
        self.assertEqual(p.returncode, 0)
        self.assertIn(",browse", p.stdout)

    def test_invalid_renderer_rejected_before_hardware(self):
        p = self.shell("--renderer", "danger")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("invalid renderer", p.stderr)

    def test_invalid_platform_rejected(self):
        p = self.shell("--platform", "x11")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("invalid platform", p.stderr)

    def test_invalid_schemes_rejected(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd", "--help",
                    "https://", "http://host/with space", "http://host/\nnext"):
            with self.subTest(url=url):
                p = self.shell("--url", url)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("URL must", p.stderr)

    def test_command_substitution_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "injected"
            p = self.shell("--url", "https://example.org/$(touch " + str(marker) + ")")
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse(marker.exists())

    def test_sandbox_disable_rejected(self):
        p = self.shell("--url", "https://example.org/",
                       env={"WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS": "1"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("sandbox disable", p.stderr)
        p = self.shell(env={"WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS": "0"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("sandbox disable", p.stderr)
        p = self.shell(env={"WEBKIT_USE_SANDBOX": "0"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("sandbox must remain", p.stderr)

    def test_missing_private_root_blocked(self):
        p = self.shell("--renderer", "software", "--platform", "headless")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("prepared private browser root", p.stderr)

    def test_grate_cannot_skip_private_root_identity(self):
        p = self.shell("--renderer", "grate",
                       env={"NURABROWSER_EXPECTED_OVERLAY_SHA256": "a" * 64})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("prepared private browser root", p.stderr)

    def test_unknown_cli_flag_and_extra_args_rejected(self):
        for args in (("--no-sandbox",), ("--platform",), ("https://example.org",)):
            with self.subTest(args=args):
                p = self.shell(*args)
                self.assertNotEqual(p.returncode, 0)

    def test_no_dynamic_shell_eval_or_system_escaping(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for pattern in (r"\beval\s", r"\bsh\s+-c\s", r"\bbash\s+-c\s",
                        r"\bssh\s", r"\bchroot\s", r"\bmount\s", r"\bsudo\s"):
            # Only code lines matter; comments are not executable.
            code = "\n".join(line for line in source.splitlines()
                             if not line.lstrip().startswith("#"))
            self.assertNotRegex(code, pattern)
        self.assertRegex(source, r'exec "\$core" --url "\$url"')


if __name__ == "__main__":
    unittest.main()
