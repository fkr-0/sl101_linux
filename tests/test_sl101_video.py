"""Device-free integration and safety tests for the SL101 software video lane."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "scripts/sl101-video-play.sh"
TRANSCODE = ROOT / "scripts/sl101-video-transcode.sh"
PROBE = ROOT / "scripts/sl101-video-probe.py"
spec = importlib.util.spec_from_file_location("sl101_video_probe", PROBE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class VideoToolingTests(unittest.TestCase):
    def test_dry_run_preserves_local_file_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "my movie - good.mp4"
            path.write_bytes(b"fixture")
            result = subprocess.run(["sh", str(PLAYER), "--dry-run", "--", str(path)],
                                    text=True, capture_output=True, check=True)
            self.assertIn(str(path), result.stdout)
            self.assertIn("no GPU", result.stdout)

    def test_missing_media_fails_closed(self):
        result = subprocess.run(["sh", str(PLAYER), "--", "/does/not/exist.mp4"],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a readable regular file", result.stderr)

    def test_missing_wayland_fails_before_playback(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "movie.mp4"
            media.write_bytes(b"fixture")
            binpath = Path(tmp) / "mpv"
            binpath.write_text("#!/bin/sh\necho '  wlshm  Wayland SHM output'\n", encoding="utf-8")
            binpath.chmod(0o755)
            env = os.environ.copy()
            env.update({"PATH": tmp + ":" + env.get("PATH", ""),
                        "XDG_RUNTIME_DIR": tmp, "WAYLAND_DISPLAY": "missing"})
            result = subprocess.run(["sh", str(PLAYER), "--", str(media)],
                                    capture_output=True, text=True, env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no Wayland socket", result.stderr)

    def test_launch_is_software_only_and_path_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "space - & $.mp4"
            media.write_bytes(b"fixture")
            capture = Path(tmp) / "mpv-args.txt"
            binpath = Path(tmp) / "mpv"
            binpath.write_text(
                "#!/bin/sh\n"
                "if [ \"$2\" = '--vo=help' ]; then echo '  wlshm  Wayland SHM output'; exit 0; fi\n"
                "printf '%s\\n' \"$@\" >\"$SL101_VIDEO_CAPTURE\"\n",
                encoding="utf-8",
            )
            binpath.chmod(0o755)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.bind(str(Path(tmp) / "wayland-0"))
                env = os.environ.copy()
                env.update({"PATH": tmp + ":" + env.get("PATH", ""),
                            "XDG_RUNTIME_DIR": tmp, "WAYLAND_DISPLAY": "wayland-0",
                            "SL101_VIDEO_CAPTURE": str(capture)})
                result = subprocess.run(
                    ["sh", str(PLAYER), "--fullscreen", "--mute", "--", str(media)],
                    capture_output=True, text=True, env=env,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            args = capture.read_text(encoding="utf-8").splitlines()
            for option in ("--hwdec=no", "--vo=wlshm", "--no-config", "--fullscreen", "--mute=yes"):
                self.assertIn(option, args)
            self.assertEqual(args[-2:], ["--", str(media)])

    def test_transcode_rejects_overwrite_and_unsupported_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mp4"
            source.write_bytes(b"fixture")
            out = Path(tmp) / "out.mp4"
            out.write_bytes(b"sentinel")
            result = subprocess.run(["sh", str(TRANSCODE), "--", str(source), str(out)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(out.read_bytes(), b"sentinel")
            result = subprocess.run(["sh", str(TRANSCODE), "--height", "1080",
                                     "--", str(source), str(Path(tmp) / "new.mp4")],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_vde_status_never_promoted_from_config_or_device(self):
        with patch.object(probe, "vde_config", return_value={"source": "/fake/config",
                                                              "value": "y"}), \
             patch.object(probe, "wayland_socket", return_value={
                 "path": "/x", "is_socket": True, "accessible": True
             }):
            report = probe.collect()
        self.assertEqual(report["vde"]["hardware_decoding_status"], "unqualified")
        self.assertEqual(report["schema"], "sl101.local-video-probe/v1")
        self.assertTrue(report["readonly"])

    def test_probe_reports_json_without_device_mutation(self):
        result = subprocess.run(["python3", str(PROBE)], check=True, capture_output=True,
                                text=True)
        payload = json.loads(result.stdout)
        self.assertIn("video_nodes", payload["vde"])
        self.assertIn("ready_for_software_launch", payload["software"])


if __name__ == "__main__":
    unittest.main()
