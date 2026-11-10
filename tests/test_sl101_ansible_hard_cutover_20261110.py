"""Offline integration regressions for the guarded hard comma-command cutover."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "deploy/ansible/tools/render_public.py"
VALIDATE = ROOT / "deploy/ansible/tools/validate_render.py"


def imported(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


renderer = imported(RENDER, "sl101_render_public")
validator = imported(VALIDATE, "sl101_validate_render")


class HardCutoverTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.template = self.root / "docs/sl101-debian-device-config"
        self.out = self.root / "generated"
        (self.template / "usr/local/bin").mkdir(parents=True)
        (self.template / "home/user/.config/sway").mkdir(parents=True)
        self.program("sl101-browse", "#!/bin/sh\nexec /usr/bin/true\n")
        self.script("home/user/.config/sway/config",
                    "bindsym $mod+b exec /usr/local/bin/sl101-browse\n")

    def script(self, relative, value):
        path = self.template / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def program(self, name, value):
        return self.script("usr/local/bin/" + name, value)

    def render(self):
        return renderer.render("debian", self.root, self.out)

    def test_generated_commands_are_marked_and_native_names(self):
        self.render()
        result = validator.validate(self.root, "debian", self.out)
        self.assertTrue(result["gate_pass"], result)
        code = (self.out / "bin/,browse").read_text()
        self.assertIn("# Managed by SL101 Ansible public-command cutover", code)
        self.assertIn("exec /usr/bin/true", code)
        self.assertIn("exec /usr/local/bin/,browse",
                      (self.out / "config/home/user/.config/sway/config").read_text())

    def test_rewrites_bare_exec_without_mangling_service_or_pid(self):
        self.program("sl101-desktop", "#!/bin/sh\nexec /usr/bin/true\n")
        self.script("home/user/.config/sway/config",
                    "exec sl101-browse\n"
                    "exec /usr/local/bin/sl101-desktop\n"
                    "exec rc-service sl101-desktop status\n"
                    "set $pid sl101-desktop.pid\n")
        self.render()
        text = (self.out / "config/home/user/.config/sway/config").read_text()
        self.assertIn("exec ,browse", text)
        self.assertIn("exec /usr/local/bin/,desktop", text)
        self.assertIn("rc-service sl101-desktop status", text)
        self.assertIn("sl101-desktop.pid", text)

    def test_privileged_and_service_helpers_are_not_public_commands(self):
        self.program("sl101-desktop", "#!/bin/sh\nexec /usr/bin/true\n")
        self.program("sl101-cog-wpe-root", "#!/bin/sh\nexec /usr/bin/true\n")
        self.render()
        result = validator.validate(self.root, "debian", self.out)
        self.assertFalse(result["gate_pass"])
        self.assertEqual(
            result["private_helpers_misclassified_as_public"],
            ["sl101-cog-wpe-root", "sl101-desktop"],
        )

    def test_missing_active_keyd_rewrite_blocks_all_deploy(self):
        self.script("etc/keyd/local.conf", "gesture = /usr/local/bin/sl101-browse\n")
        self.render()
        result = validator.validate(self.root, "debian", self.out)
        self.assertFalse(result["gate_pass"])
        self.assertTrue(any(x["file"] == "etc/keyd/local.conf"
                            for x in result["unresolved_references"]))

    def test_hidden_old_executable_in_rendered_code_is_rejected(self):
        self.render()
        p = self.out / "bin/,browse"
        p.write_text(p.read_text() + "\nexec /usr/local/bin/sl101-browse\n")
        result = validator.validate(self.root, "debian", self.out)
        self.assertFalse(result["gate_pass"])

    def test_quoted_help_heredoc_does_not_false_positive(self):
        self.program("sl101-browse",
                     "#!/bin/sh\nusage(){\ncat <<'EOF'\n"
                     "Usage: sl101-browse\n sl101-browse --url URL\nEOF\n}\n")
        self.render()
        result = validator.validate(self.root, "debian", self.out)
        self.assertTrue(result["gate_pass"], result)

    def test_xdg_exec_bare_name_must_be_rewritten(self):
        self.script("usr/share/applications/browser.desktop",
                    "[Desktop Entry]\nType=Application\nExec=sl101-browse %u\n")
        self.render()
        report = validator.validate(self.root, "debian", self.out)
        self.assertFalse(report["gate_pass"])
        self.assertIn("Exec=sl101-browse", report["unresolved_references"][0]["text"])

    def test_command_name_collision_blocks_render(self):
        self.program("sl101-browse", "#!/bin/sh\necho hello\n")
        source = self.root / "deploy/ansible/public/debian/,browse"
        source.parent.mkdir(parents=True)
        source.write_text("#!/bin/sh\necho foreign\n")
        with self.assertRaisesRegex(ValueError, "Duplicate canonical"):
            self.render()

    def test_no_candidate_module_or_live_device_touch(self):
        self.render()
        for p in self.out.rglob("*"):
            if p.is_file():
                self.assertNotIn("192.168.23.106", p.read_text())
        playbook = (ROOT / "deploy/ansible/playbooks/site.yml").read_text()
        self.assertIn("validate_render.py", playbook)
        self.assertIn("delegate_to: localhost", playbook)
        self.assertIn("SL101_APPLY", playbook)
        entry = (ROOT / "deploy/ansible/entrypoint.sh").read_text()
        self.assertIn('SL101_CUTOVER:-NO', entry)

    def test_refuse_apply_before_controller_stage(self):
        ep = ROOT / "deploy/ansible/entrypoint.sh"
        run = subprocess.run(["sh", str(ep), "apply"],
                             capture_output=True, text=True,
                             env={"DEPLOY_TARGET": "sl101-nura",
                                  "DEPLOY_PROFILE": "nura",
                                  "SL101_APPLY": "YES",
                                  "SL101_CUTOVER": "NO"})
        self.assertEqual(run.returncode, 65)
        self.assertIn("SL101_CUTOVER=YES", run.stderr)

    def test_remote_canonical_collision_guard(self):
        tasks = (ROOT / "deploy/ansible/playbooks/user-commands.yml").read_text()
        self.assertIn("Refuse to overwrite unrelated comma-named commands", tasks)
        self.assertIn("public_existing_content", tasks)
        self.assertIn("legacy-bin", tasks)

    def test_full_existing_profiles_are_syntactically_renderable(self):
        for p in ("nura", "debian"):
            with self.subTest(profile=p):
                output = self.root / ("actual-" + p)
                result = renderer.render(p, ROOT, output)
                self.assertIn(",browse", result["commands"])
                self.assertGreater(len(result["commands"]), 8)
                check = validator.validate(ROOT, p, output)
                self.assertIsInstance(check["unresolved_references"], list)


if __name__ == "__main__":
    unittest.main()
