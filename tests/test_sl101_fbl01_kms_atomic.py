"""Host-only behavioral tests for the remote KMS safety wrapper.

The embedded remote shell is extracted and rewritten to a fully mocked local
filesystem/command environment. No SSH, DRM, desktop service or GPU is used.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "scripts/sl101-fbl01-kms-atomic-capture.sh").read_text()
REMOTE = SCRIPT.split("<<'REMOTE'\n", 1)[1].rsplit("\nREMOTE", 1)[0]


class TestAtomicCapture(unittest.TestCase):
    def test_pinned_identity(self):
        self.assertIn("user@192.168.23.106", SCRIPT)
        self.assertIn("7.0.1-postmarketos-grate", SCRIPT)
        self.assertIn("ASUS Eee Pad Slider SL101", SCRIPT)
        self.assertIn("DRY RUN: no mutation", SCRIPT)

    def run_mock(self, behavior, signal=None, desktop="started", limit=2):
        with tempfile.TemporaryDirectory(prefix="fbl01-mock-") as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            debug = root / "debug"
            debug.write_text("0x0c\n")
            desktop_file = root / "desktop"
            desktop_file.write_text(desktop)
            pid_file = root / "grandchild.pid"
            for name, body in {
                "hostname": "echo sl101-nura",
                "uname": "echo 7.0.1-postmarketos-grate",
                "grep": 'if [ "$1" = "-aq" ]; then exit 0; fi; exec /usr/bin/grep "$@"',
                "dmesg": "echo mock-kernel",
                "strace": "exit 0",
                "sl101-kms-run": "exit 0",
                "rc-service": f'''case "$2" in
status) cat "{desktop_file}"; [ "$(cat "{desktop_file}")" = started ];;
start) echo started > "{desktop_file}";;
*) exit 2;;
esac''',
                "test-child": behavior.replace("@PID@", str(pid_file)).replace("@DESKTOP@", str(desktop_file)),
            }.items():
                path = bin_dir / name
                path.write_text("#!/bin/sh\n" + body + "\n")
                path.chmod(0o755)
            # Script under test is the actual remote body, with only protected
            # device paths, output directory, deadline and mock executable changed.
            body = REMOTE.replace("/proc/device-tree/model", str(root / "model"))
            body = body.replace("/sys/module/drm/parameters/debug", str(debug))
            body = body.replace("/usr/local/bin/sl101-cog-drm-root-cpu", str(bin_dir / "test-child"))
            body = body.replace("out=/tmp/sl101-fbl01-kms-atomic-20261103", f"out={root}/capture")
            body = body.replace(" + 75)", f" + {limit})")
            body = body.replace("sleep 2\n  kill -KILL", "sleep 0.1\n  kill -KILL")
            body = body.replace(
                "setsid sh -c 'exec strace -f -tt -v -s 256 -e trace=ioctl -o \"$1\" sl101-kms-run --timeout 35 -- " +
                str(bin_dir / "test-child") + " --gpu https://example.org' sh \"$out.strace.log\"",
                "setsid sh -c 'exec test-child'",
            )
            body = body.replace("test -x " + str(bin_dir / "test-child"), "true")
            runner = root / "remote.sh"
            runner.write_text(body)
            proc = subprocess.Popen(
                ["sh", str(runner), "--execute"],
                env={**os.environ, "PATH": str(bin_dir) + ":" + os.environ["PATH"]},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                if signal is not None:
                    time.sleep(0.6)
                    proc.send_signal(signal)
                stdout, stderr = proc.communicate(timeout=limit + 9)
                grandchild = pid_file.read_text().strip() if pid_file.exists() else None
                if grandchild:
                    # PID can be a zombie briefly; /proc status shows whether
                    # a runnable child survived the process-group cleanup.
                    state_path = Path("/proc") / grandchild / "status"
                    state = state_path.read_text() if state_path.exists() else ""
                    alive = bool(state) and "\nState:\tZ" not in state
                else:
                    alive = False
                return proc.returncode, stdout, stderr, debug.read_text(), desktop_file.read_text(), alive
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()

    def test_success_restores_debug_and_desktop(self):
        rc, out, err, debug, desktop, alive = self.run_mock("exit 0")
        self.assertEqual((rc, debug, desktop, alive), (0, "0x0c\n", "started", False), (out, err))

    def test_failure_restores_debug_and_desktop(self):
        rc, out, err, debug, desktop, alive = self.run_mock("exit 42")
        self.assertEqual((rc, debug, desktop, alive), (42, "0x0c\n", "started", False), (out, err))

    def test_timeout_cleans_nested_child(self):
        rc, out, err, debug, desktop, alive = self.run_mock("sleep 120 & echo $! > @PID@; wait", limit=2)
        self.assertEqual(rc, 124, (out, err))
        self.assertFalse(alive, (out, err))
        self.assertEqual(debug, "0x0c\n")
        self.assertEqual(desktop, "started")

    def test_sigterm_cleans_nested_child(self):
        import signal
        rc, out, err, debug, desktop, alive = self.run_mock(
            "sleep 120 & echo $! > @PID@; wait", signal=signal.SIGTERM
        )
        self.assertEqual(rc, 143, (out, err))
        self.assertFalse(alive, (out, err))
        self.assertEqual(debug, "0x0c\n")

    def test_success_restores_desktop_after_launcher_stops_it(self):
        rc, out, err, debug, desktop, alive = self.run_mock("echo stopped > @DESKTOP@; exit 0")
        self.assertEqual((rc, desktop, debug), (0, "started\n", "0x0c\n"), (out, err))

    def test_failure_restores_desktop_after_launcher_stops_it(self):
        rc, out, err, debug, desktop, alive = self.run_mock("echo stopped > @DESKTOP@; exit 42")
        self.assertEqual((rc, desktop, debug), (42, "started\n", "0x0c\n"), (out, err))

    def test_previously_stopped_desktop_remains_stopped(self):
        rc, out, err, debug, desktop, alive = self.run_mock("exit 0", desktop="stopped")
        self.assertEqual((rc, desktop, debug), (0, "stopped", "0x0c\n"), (out, err))


if __name__ == "__main__":
    unittest.main()
