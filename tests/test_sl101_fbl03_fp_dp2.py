"""Lane 03: patch contracts and compiled host lowering regression; no GPU pixels."""
from pathlib import Path
import os
import json
import runpy
from unittest import mock
import shutil
import tempfile
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
DP2 = ROOT / "patches/mesa-25.0.7/0037-grate-fp-dp2.patch"
DOT = ROOT / "patches/mesa-25.0.7/0012-grate-fp-frc-dp3-dp4.patch"


class FPDP2Patch(unittest.TestCase):
    def test_dp2_reuses_scalar_dot_lowerer(self):
        dp2, dot = DP2.read_text(), DOT.read_text()
        self.assertRegex(dp2, r"fp_emit_dp2\([^;]*?\+\{\n\+   return fp_emit_dot\(fp, lowering, tgsi_inst, 2\);")
        self.assertIn("+            case TGSI_OPCODE_DP2:", dp2)
        self.assertIn("+               fp_emit_dp2(fp, &lowering, inst);", dp2)
        for dimension in (3, 4):
            self.assertIn(f"return fp_emit_dot(fp, lowering, tgsi_inst, {dimension});", dot)
        self.assertIn("op.Instruction.Opcode = c == 0 ? TGSI_OPCODE_MUL : TGSI_OPCODE_MAD;", dot)
        self.assertIn("fp_dot_scratch", dot)
        self.assertIn("source_mask", dot)
        self.assertIn("direct_final = false;", dot)

    def test_compiled_native_dp2_regression(self):
        # Optional unit test for developer hosts; explicit qualification is NEVER optional.
        runner = ROOT / "scripts/sl101-fbl03-native-qualify.py"
        build = ROOT / "build/mesa-grate-clean/mesa-25.0.7/builddir/build.ninja"
        self.assertTrue(runner.is_file(), "tracked native qualification runner missing")
        if not build.is_file():
            self.skipTest("configured Mesa build absent; run explicit native qualification")
        result = subprocess.run([sys.executable, str(runner)], cwd=ROOT,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: 14 grate FRC/DP lowering structural tests", result.stdout)

    def test_release_ndebug_cannot_disable_native_assertions(self):
        # Ninja wrapper injects the inherited release flag into real commands.
        build = ROOT / "build/mesa-grate-clean/mesa-25.0.7/builddir/build.ninja"
        if not build.is_file():
            self.skipTest("developer host lacks Mesa; explicit qualification is mandatory")
        ninja = shutil.which("ninja")
        self.assertIsNotNone(ninja)
        with tempfile.TemporaryDirectory(prefix="sl101-fbl03-ndebug-") as td:
            wrapper = Path(td) / "ninja"
            wrapper.write_text(
                "#!/usr/bin/env python3\n"
                "import subprocess, sys\n"
                f"r = subprocess.run([{ninja!r}, *sys.argv[1:]], capture_output=True, text=True)\n"
                "if '-t' in sys.argv and 'commands' in sys.argv:\n"
                "    print('\\n'.join(line + ' -DNDEBUG' for line in r.stdout.splitlines()))\n"
                "else:\n"
                "    print(r.stdout, end='')\n"
                "print(r.stderr, file=sys.stderr, end='')\n"
                "sys.exit(r.returncode)\n"
            )
            wrapper.chmod(0o755)
            env = dict(os.environ, PATH=td + os.pathsep + os.environ.get("PATH", ""))
            runner = ROOT / "scripts/sl101-fbl03-native-qualify.py"
            normal = subprocess.run([sys.executable, str(runner)], cwd=ROOT,
                                    env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(normal.returncode, 0, normal.stdout + normal.stderr)
            self.assertIn("PASS: 14", normal.stdout)
            negative = subprocess.run([sys.executable, str(runner), "--assertion-canary"],
                                      cwd=ROOT, env=env, capture_output=True, text=True,
                                      timeout=120)
            self.assertNotEqual(negative.returncode, 0, negative.stdout + negative.stderr)
            self.assertIn("FAIL: FBL03 native qualification", negative.stderr)
            self.assertNotIn("PASS: 14", negative.stdout)

    def test_strict_native_fails_missing_input_hash_and_replay(self):
        # Test runner fail-closed paths without changing committed inputs.
        runner = ROOT / "scripts/sl101-fbl03-native-qualify.py"
        original = json.loads((ROOT / "tests/fixtures/sl101-fbl03-native/manifest.json").read_text())
        qualify = runpy.run_path(str(runner), run_name="fbl03_negative_test")["qualify"]
        build = ROOT / "build/mesa-grate-clean/mesa-25.0.7/builddir"
        first_input = next(iter(original["inputs"]))
        cases = (
            ("missing_input", lambda m: m["inputs"].update({"absent-fixture.c": "0" * 64}),
             RuntimeError, "missing required input"),
            ("input_hash", lambda m: m["inputs"].update({first_input: "0" * 64}),
             RuntimeError, "SHA-256 mismatch"),
            ("patch_replay", lambda m: m["patch_order"].insert(1, m["patch_order"][0]),
             subprocess.CalledProcessError, None),
            ("patched_source_hash", lambda m: m.update(patched_sha256="0" * 64),
             RuntimeError, "SHA-256 mismatch"),
        )
        with tempfile.TemporaryDirectory(prefix="sl101-fbl03-negative-") as td:
            for name, mutate, error_type, message in cases:
                with self.subTest(name=name):
                    manifest = json.loads(json.dumps(original))
                    mutate(manifest)
                    path = Path(td) / (name + ".json")
                    path.write_text(json.dumps(manifest))
                    with mock.patch.dict(qualify.__globals__, {"MANIFEST": path}):
                        with self.assertRaises(error_type) as captured:
                            qualify(build)
                    if message:
                        self.assertIn(message, str(captured.exception))

    def test_native_qualification_fails_missing_build(self):
        runner = ROOT / "scripts/sl101-fbl03-native-qualify.py"
        result = subprocess.run([sys.executable, str(runner), "--mesa-build",
                                 str(ROOT / "tests/fixtures/sl101-fbl03-native/no-build")],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing configured Mesa build.ninja", result.stderr)

    def test_no_cap_spoof(self):
        text = DP2.read_text()
        self.assertEqual(text.count("--- a/"), 1)
        self.assertNotRegex(text, r"PIPE_CAP|GL_MAX|MAX_FRAGMENT_UNIFORM")


if __name__ == "__main__":
    unittest.main()
