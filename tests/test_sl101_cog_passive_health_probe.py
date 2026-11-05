"""Host-only safety and parsing checks for passive SL101 device telemetry."""
import importlib.util
from pathlib import Path
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/sl101-cog-passive-health-probe.py"
spec = importlib.util.spec_from_file_location("sl101_passive_health_probe", SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def good(**overrides):
    result = {
        "hostname": "sl101-nura",
        "kernel": "7.0.1-postmarketos-grate",
        "cid": "035344534c31323880ac79a543010300",
        "boot_id": "ccfb94d1-a56a-4419-96ef-42c632bb0b46",
        "renderer": "SL101_DESKTOP_RENDERER=grate",
        "processes": [{"comm": "labwc", "pid": 123, "state": "S", "start_ticks": "10"}],
        "chroot_mount_count": 12,
        "memory": {"MemAvailable": "800 kB"},
    }
    result.update(overrides)
    return result


class PassiveHealthTest(unittest.TestCase):
    def test_identity_passes_for_fixed_target(self):
        self.assertEqual(probe.validate(good()), good()["boot_id"])

    def test_fail_closed_on_wrong_host_kernel_cid_or_renderer(self):
        for name, value in [
            ("hostname", "another-host"), ("kernel", "another-kernel"),
            ("cid", "another-card"), ("renderer", "SL101_DESKTOP_RENDERER=pixman"),
        ]:
            with self.subTest(name=name), self.assertRaises(probe.SafetyGate):
                probe.validate(good(**{name: value}))

    def test_refuse_reboot_mid_probe(self):
        records = iter([good(), good(boot_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")])
        with self.assertRaisesRegex(probe.SafetyGate, "boot_changed"):
            probe.collect(samples=2, interval=.5, runner=lambda: next(records),
                          pause=lambda _: None)

    def test_refuse_missing_processes(self):
        with self.assertRaisesRegex(probe.SafetyGate, "no_desktop_or_browser"):
            probe.validate(good(processes=[]))

    def test_bounded_sampling_and_no_remote_mutation(self):
        for n, interval in [(0, 1), (13, 1), (1, .1), (1, 3)]:
            with self.subTest(n=n, interval=interval), self.assertRaises(ValueError):
                probe.collect(samples=n, interval=interval, runner=good)
        data = probe.collect(samples=3, interval=.5, runner=good, pause=lambda _: None)
        self.assertEqual([x["sample_index"] for x in data], [0, 1, 2])
        self.assertIn("read(", probe.REMOTE_PY)
        for forbidden in ("os.system", "subprocess", "kill(", "mount(", "open('/dev/input",
                          'open("/dev/input', "udevadm trigger", "coredump"):
            self.assertNotIn(forbidden, probe.REMOTE_PY)

    def test_kernel_fault_matcher_is_specific(self):
        self.assertIsNotNone(probe.FAULT_PATTERN.search("tegra_drm_sched_timedout_job"))
        self.assertIsNotNone(probe.FAULT_PATTERN.search("host1x scheduler timeout"))
        self.assertIsNotNone(probe.FAULT_PATTERN.search("oom-kill: process 7"))
        self.assertIsNone(probe.FAULT_PATTERN.search("normal tegra GR3D initialization"))

    def test_python_syntax(self):
        result = subprocess.run(["python3", "-m", "py_compile", str(SOURCE)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
