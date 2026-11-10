"""Host-only regression tests for hard comma public-command cutover audit."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/sl101-public-command-audit.py"
SPEC = importlib.util.spec_from_file_location("sl101_public_command_audit", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PublicCommandAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.public = self.root / "public"
        self.refs = self.root / "refs"
        self.public.mkdir()
        self.refs.mkdir()

    def write(self, relative, contents="#!/bin/sh\necho ok\n"):
        p = self.root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents)
        return p

    def scan(self):
        return MODULE.audit(self.root, ("public",), ("refs",))

    def test_old_binaries_and_absolute_callers_are_reported(self):
        self.write("public/sl101-browse")
        self.write("public/sl101-desktop")
        self.write("refs/sway.conf",
                   "bindsym $mod+b exec /usr/local/bin/sl101-browse --url about:blank\n"
                   "exec_always --no-startup-id sl101-desktop\n")
        report = self.scan()
        self.assertFalse(report["gate_pass"])
        self.assertEqual(report["legacy_count"], 2)
        names = {x["name"]: x for x in report["commands"]}
        self.assertEqual(names["sl101-browse"]["proposed"], ",browse")
        self.assertEqual(len(names["sl101-browse"]["references"]), 1)
        self.assertEqual(len(names["sl101-desktop"]["references"]), 1)
        self.assertEqual(report["reference_count"], 2)

    def test_canonical_commands_have_no_duplicate_manifest(self):
        self.write("public/,browse")
        self.write("public/,files")
        self.write("refs/sway.conf", "bindsym $mod+b exec ,browse\n")
        report = self.scan()
        self.assertTrue(report["gate_pass"], report)
        self.assertEqual(report["canonical_count"], 2)
        self.assertEqual(report["legacy_count"], 0)

    def test_stale_caller_rejected_after_hard_rename(self):
        self.write("public/,browse")
        self.write("refs/sway.conf", "bindsym $mod+b exec sl101-browse\n")
        report = self.scan()
        self.assertFalse(report["gate_pass"])
        self.assertEqual([x["legacy"] for x in report["stale_references"]],
                         ["sl101-browse"])
        self.assertEqual(report["stale_references"][0]["references"][0]["line"], 1)

    def test_nuraloumi_old_name_is_detected_from_canonical(self):
        self.write("public/,files")
        self.write("refs/start.sh", "nuraloumi-files --help\n")
        report = self.scan()
        self.assertFalse(report["gate_pass"])
        self.assertEqual(report["stale_references"][0]["legacy"], "nuraloumi-files")

    def test_a_symlink_is_never_followed_or_accepted(self):
        external = self.write("real-tool", "#!/bin/sh\n")
        (self.public / ",browse").symlink_to(external)
        report = self.scan()
        self.assertFalse(report["gate_pass"])
        self.assertEqual(report["commands"][0]["status"], "symlink-not-allowed")

    def test_public_collision_detected_without_alias_registry(self):
        self.write("public/,browse")
        self.write("public/sl101-browse")
        report = self.scan()
        self.assertFalse(report["gate_pass"])
        self.assertEqual(report["collisions"][0]["command"], ",browse")

    def test_synthetic_binary_and_markdown_not_treated_as_callers(self):
        self.write("public/sl101-browse")
        self.write("refs/README.md", "sl101-browse is historical\n")
        self.write("refs/bin.sh", b"\0sl101-browse".decode("latin-1"))
        report = self.scan()
        self.assertEqual(report["reference_count"], 0)

    def test_shell_comment_is_not_an_active_caller(self):
        self.write("public/sl101-browse")
        self.write("refs/start.sh", "# sl101-browse old\n"
                   "echo other\n")
        self.assertEqual(self.scan()["reference_count"], 0)

    def test_suffixless_public_scripts_are_scanned_for_calls(self):
        self.write("public/sl101-browse")
        self.write("public/sl101-open", "exec sl101-browse \"$@\"\n")
        report = self.scan()
        open_cmd = {c["name"]: c for c in report["commands"]}
        self.assertEqual(len(open_cmd["sl101-browse"]["references"]), 1)

    def test_paths_may_not_escape_repo(self):
        with self.assertRaises(ValueError):
            MODULE.audit(self.root, ("../../../../tmp",), ("refs",))

    def test_markdown_has_source_and_line(self):
        self.write("public/sl101-browse")
        self.write("refs/sway.conf", "exec /usr/local/bin/sl101-browse\n")
        markdown = MODULE.markdown(self.scan())
        self.assertIn("sl101-browse", markdown)
        self.assertIn("refs/sway.conf:1", markdown)

    def test_cli_gate_is_nonzero_without_mutations(self):
        self.write("public/sl101-browse")
        args = [sys.executable, str(TOOL), "--root", str(self.root),
                "--public-dir", "public", "--refs-dir", "refs",
                "--format", "json", "--gate"]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(json.loads(result.stdout)["gate_pass"])
        self.assertTrue((self.public / "sl101-browse").exists())

    def test_cli_gate_pass_after_full_rename(self):
        self.write("public/,browse")
        args = [sys.executable, str(TOOL), "--root", str(self.root),
                "--public-dir", "public", "--refs-dir", "refs",
                "--format", "json", "--gate"]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["gate_pass"])


if __name__ == "__main__":
    unittest.main()
