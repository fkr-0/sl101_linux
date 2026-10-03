import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sl101_kernel_coherence",
    ROOT / "scripts/sl101-kernel-coherence.py",
)
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)


RUNTIME_CONFIG = """\
CONFIG_MFD_ASUS_TRANSFORMER_EC=y
CONFIG_SERIO_ASUS_TRANSFORMER_EC=y
CONFIG_ZRAM=y
CONFIG_NF_TABLES=m
"""

BUILTINS = """\
kernel/drivers/mfd/asus-transformer-ec.ko
kernel/drivers/input/serio/asus-transformer-ec-kbc.ko
"""


def write_fixture(
    root: Path,
    *,
    runtime_config: str = RUNTIME_CONFIG,
    boot_config: str = RUNTIME_CONFIG,
    module_tree: bool = True,
    stale_ec_modules: bool = False,
) -> None:
    (root / "proc/sys/kernel").mkdir(parents=True)
    (root / "proc/sys/kernel/osrelease").write_text("6.18.45\n")
    with gzip.open(root / "proc/config.gz", "wt") as handle:
        handle.write(runtime_config)

    (root / "boot").mkdir()
    (root / "boot/config").write_text(boot_config)

    if not module_tree:
        return

    module_root = root / "lib/modules/6.18.45"
    module_root.mkdir(parents=True)
    (module_root / "modules.builtin").write_text(BUILTINS)
    if stale_ec_modules:
        ec = module_root / "kernel/drivers/mfd/asus-transformer-ec.ko"
        kbc = module_root / "kernel/drivers/input/serio/asus-transformer-ec-kbc.ko"
        ec.parent.mkdir(parents=True)
        kbc.parent.mkdir(parents=True)
        ec.write_bytes(b"fixture")
        kbc.write_bytes(b"fixture")


class KernelCoherenceTests(unittest.TestCase):
    def test_coherent_fixture_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_fixture(root)
            result = m.analyze(m.collect_root(root))
            self.assertTrue(result["coherent"])
            self.assertEqual(result["summary"]["errors"], 0)
            self.assertEqual(result["summary"]["config_difference_count"], 0)

    def test_config_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            boot = """\
CONFIG_MFD_ASUSEC=m
CONFIG_SERIO_ASUSEC=m
CONFIG_ZRAM=m
CONFIG_NF_TABLES=m
"""
            write_fixture(root, boot_config=boot)
            result = m.analyze(m.collect_root(root))
            self.assertFalse(result["coherent"])
            codes = [finding["code"] for finding in result["findings"]]
            self.assertIn("kernel_config_mismatch", codes)
            mismatch = next(
                finding
                for finding in result["findings"]
                if finding["code"] == "kernel_config_mismatch"
            )
            symbols = {item["symbol"] for item in mismatch["differences"]}
            self.assertIn("CONFIG_MFD_ASUS_TRANSFORMER_EC", symbols)
            self.assertIn("CONFIG_MFD_ASUSEC", symbols)

    def test_missing_module_tree_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_fixture(root, module_tree=False)
            result = m.analyze(m.collect_root(root))
            self.assertFalse(result["coherent"])
            self.assertIn(
                "module_tree_missing",
                [finding["code"] for finding in result["findings"]],
            )

    def test_stale_ec_module_files_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_fixture(root, stale_ec_modules=True)
            result = m.analyze(m.collect_root(root))
            self.assertFalse(result["coherent"])
            stale = [
                finding
                for finding in result["findings"]
                if finding["code"] == "builtin_has_stale_module_file"
            ]
            self.assertEqual(len(stale), 2)
            self.assertEqual(
                {finding["module"] for finding in stale},
                {"asus-transformer-ec", "asus-transformer-ec-kbc"},
            )

    def test_missing_builtin_metadata_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_fixture(root)
            (root / "lib/modules/6.18.45/modules.builtin").write_text("")
            result = m.analyze(m.collect_root(root))
            self.assertFalse(result["coherent"])
            metadata = [
                finding
                for finding in result["findings"]
                if finding["code"] == "builtin_metadata_mismatch"
            ]
            self.assertEqual(len(metadata), 2)

    def test_cli_is_deterministic_and_nonzero_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_fixture(root, stale_ec_modules=True)
            argv = [
                str(ROOT / "scripts/sl101-kernel-coherence.py"),
                "--root",
                str(root),
            ]
            first = subprocess.run(argv, text=True, capture_output=True, check=False)
            second = subprocess.run(argv, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 1)
            self.assertEqual(second.returncode, 1)
            self.assertEqual(first.stdout, second.stdout)
            payload = json.loads(first.stdout)
            self.assertFalse(payload["coherent"])
            self.assertEqual(
                payload["schema"],
                "android-infra.sl101-kernel-coherence.v1",
            )


if __name__ == "__main__":
    unittest.main()
