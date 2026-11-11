#!/usr/bin/env python3
"""Native NuraBrowser IPC client against a bounded, real Unix-socket fixture."""
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "launch.sh"


class LauncherOptionTests(unittest.TestCase):
    def launch(self, *args):
        env = os.environ.copy()
        env.pop("NURABROWSER_PRIVATE_ROOT", None)
        return subprocess.run(["sh", str(LAUNCHER), *args],
                              env=env, capture_output=True, text=True,
                              timeout=5)

    def test_usage_exposes_one_public_command(self):
        result = self.launch("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn(",browse --command", result.stdout)

    def test_fail_closed_remote_argument_combinations(self):
        cases = (
            (("--command", "open"), "requires explicit --url"),
            (("--command", "reload", "--url", "https://example.org"), "only accepted"),
            (("--command", "uri", "--renderer", "grate"), "cannot change renderer"),
            (("--command", "back", "--platform", "drm"), "cannot change renderer"),
            (("--command", "shutdown"), "invalid command"),
            (("--command=",), "empty --command"),
            (("--command", "uri", "--command", "back"), "specified once"),
            (("--command", "open", "--url", "file:///etc/passwd"), "absolute whitespace-free"),
        )
        for args, expected in cases:
            with self.subTest(args=args):
                result = self.launch(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_valid_remote_command_reaches_private_root_gate(self):
        result = self.launch("--command", "uri")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not inside the prepared private browser root", result.stderr)
        self.assertNotIn("invalid command", result.stderr)


class BrowserRemoteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not hasattr(cls, "binary"):
            raise unittest.SkipTest(
                "compiled C client required; run tests/run-remote-host.sh"
            )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nura-browser-remote-")
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name) / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.path = self.runtime / "nura-browser.sock"

    def call(self, *args, runtime=None):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = str(runtime if runtime is not None else self.runtime)
        return subprocess.run([self.binary, *args], env=env, capture_output=True,
                              text=True, timeout=6)

    @contextlib.contextmanager
    def server(self, response=None, *, mode=0o600, read_request=True):
        requests = []
        errors = []
        sock = socket.socket(socket.AF_UNIX)
        sock.settimeout(5)
        sock.bind(str(self.path))
        self.path.chmod(mode)
        sock.listen(1)

        def worker():
            try:
                conn, _ = sock.accept()
                with conn:
                    conn.settimeout(5)
                    request = bytearray()
                    if read_request:
                        while b"\n" not in request:
                            data = conn.recv(1024)
                            if not data:
                                raise ValueError("premature client EOF")
                            request.extend(data)
                            if len(request) > 8192:
                                raise ValueError("oversized client request")
                        requests.append(json.loads(request))
                    answer = response
                    if answer is None:
                        answer = json.dumps(
                            {"ok": True, "result": {"command": requests[0]["command"]}}
                        ).encode() + b"\n"
                    if answer:
                        conn.sendall(answer)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            yield requests, errors
        finally:
            thread.join(timeout=6)
            sock.close()
            self.path.unlink(missing_ok=True)
            self.assertFalse(thread.is_alive(), "test server leaked")

    def test_all_commands_and_structured_json_reply(self):
        examples = (
            ("uri", None), ("back", None), ("forward", None),
            ("reload", None), ("stop", None),
            ("open", "https://example.org/?q=über&x=%20"),
        )
        for command, argument in examples:
            with self.subTest(command=command):
                args = [command] + ([argument] if argument is not None else [])
                with self.server() as (requests, errors):
                    result = self.call(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["result"]["command"], command)
                self.assertEqual(requests, [{"command": command}] if argument is None else
                                 [{"command": command, "argument": argument}])
                self.assertFalse(errors)

    def test_remote_failure_not_leaked_to_stdout(self):
        with self.server(b'{"ok":false,"error":"navigation_failed"}\n') as (_, errors):
            result = self.call("back")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("rejected", result.stderr)
        self.assertFalse(errors)

    def test_invalid_commands_rejected_before_connecting(self):
        for args in (
            (), ("execute",), ("reload", "https://example.org"),
            ("open",), ("open", ""), ("open", "https://example.org", "extra"),
            ("open", "https://example.org/\r\nbad"),
            ("open", "https://example.org/" + "a" * 4096),
        ):
            with self.subTest(args=args):
                result = self.call(*args)
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_no_socket_or_insecure_socket(self):
        self.assertEqual(self.call("uri").returncode, 1)
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(self.path))
        sock.listen(1)
        self.path.chmod(0o666)
        try:
            self.assertEqual(self.call("uri").returncode, 1)
        finally:
            sock.close()
            self.path.unlink()

    def test_reject_socket_symlink_and_bad_runtime(self):
        dummy = self.runtime / "other"
        dummy.write_text("not a socket")
        self.path.symlink_to(dummy)
        self.assertEqual(self.call("uri").returncode, 1)
        self.path.unlink()
        self.runtime.chmod(0o755)
        self.assertEqual(self.call("uri").returncode, 1)
        self.runtime.chmod(0o700)
        alias = Path(self.tmp.name) / "alias"
        alias.symlink_to(self.runtime, target_is_directory=True)
        self.assertEqual(self.call("uri", runtime=alias).returncode, 1)
        self.assertEqual(self.call("uri", runtime=self.runtime / ".." / "runtime").returncode, 1)

    def test_reject_invalid_and_oversized_server_response(self):
        bad_replies = (
            b"not json\n",
            b'{"ok":"true","result":null}\n',
            b'{"ok":true}\n',
            b'{"ok":true,"result":null}',  # missing newline
            b'{"ok":true,"result":null}\nsecond\n',
            b'{"ok":true,"result":"\x00"}\n',
            b'{"ok":true,"result":"' + b"a" * 9000 + b'"}\n',
        )
        for response in bad_replies:
            with self.subTest(reply_len=len(response)):
                with self.server(response=response) as (_, errors):
                    result = self.call("uri")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(result.stdout, "")
                self.assertFalse(errors, errors)


if __name__ == "__main__":
    executable = sys.argv[1]
    sys.argv = [sys.argv[0]]
    BrowserRemoteTest.binary = executable
    unittest.main(verbosity=2)
