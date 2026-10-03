import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rb",
    ROOT / "scripts/sl101-rawboot.py",
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def zi(n=2 * 1024 * 1024):
    data = bytearray(n)
    data[0x24:0x28] = m.ZIMAGE_MAGIC
    struct.pack_into("<I", data, 0x28, 0x10008000)
    struct.pack_into("<I", data, 0x2C, 0x10008000 + n)
    return bytes(data)


def dt(payload=b"asus,sl101\0"):
    size = 40 + len(payload)
    data = bytearray(size)
    data[:4] = m.FDT_MAGIC
    struct.pack_into(">I", data, 4, size)
    data[40:] = payload
    return bytes(data)


def image(kernel, dtb, page=2048):
    header = bytearray(page)
    header[:8] = m.ANDROID_MAGIC
    struct.pack_into(
        "<10I",
        header,
        8,
        len(kernel) + len(dtb),
        0x10008000,
        0,
        0,
        0,
        0,
        0x10000100,
        page,
        0,
        0,
    )
    return bytes(header) + kernel + dtb


class T(unittest.TestCase):
    def test_inspect_header_payload_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dev"
            kernel = zi()
            dtb = dt(b"asus,sl101-ec-dock\0embedded-controller@19\0")
            path.write_bytes(b"X" * 4096 + image(kernel, dtb) + b"T" * 99)
            result = m.inspect(path, 4096)
            self.assertEqual(
                result["header_kernel_size"],
                len(kernel) + len(dtb),
            )
            self.assertTrue(result["dtb_has_sl101_ec"])

    def test_reject_bad_header_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dev"
            kernel = zi()
            dtb = dt()
            raw = bytearray(image(kernel, dtb))
            struct.pack_into("<I", raw, 8, 1)
            path.write_bytes(raw)
            with self.assertRaises(m.ContractError):
                m.inspect(path, 0)

    def test_write_patches_header_and_restore(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            device = root / "dev"
            old_kernel = zi()
            old_dtb = dt()
            raw = image(old_kernel, old_dtb)
            slot_size = len(raw) + 8192
            device.write_bytes(raw + b"T" * (slot_size - len(raw)))

            new_kernel = root / "k"
            new_dtb = root / "d"
            new_kernel.write_bytes(zi())
            new_dtb.write_bytes(
                dt(b"asus,sl101-ec-dock\0embedded-controller@19\0")
            )

            class Args:
                pass

            args = Args()
            args.device = str(device)
            args.lnx_offset = 0
            args.slot_size = slot_size
            args.kernel = str(new_kernel)
            args.dtb = str(new_dtb)
            args.expected_kernel_sha256 = m.sha256_bytes(old_kernel)
            args.expected_dtb_sha256 = m.sha256_bytes(old_dtb)

            plan = m.make_plan(args)
            backup_dir = root / "bak"
            info = m.backup_slot(
                device,
                0,
                slot_size,
                backup_dir,
                plan["current"],
            )
            m.write_target(device, plan, new_kernel, new_dtb)
            readback = m.verify_target(device, plan)
            self.assertEqual(
                readback["header_kernel_size"],
                len(new_kernel.read_bytes()) + len(new_dtb.read_bytes()),
            )

            contract = dict(
                contract="sl101-rawboot-restore-v2",
                device=str(device),
                lnx_offset=0,
                slot_size=slot_size,
                slot_sha256=info["slot_sha256"],
            )
            m.restore(
                device,
                backup_dir / "slot-backup.json",
                m.token(contract),
            )
            self.assertEqual(
                m.inspect(device, 0)["dtb_sha256"],
                m.sha256_bytes(old_dtb),
            )


if __name__ == "__main__":
    unittest.main()
