#!/usr/bin/env python3
"""SL101 .106: exact dmafix1 candidate SD default and ONE-SHOT RAM kexec.

No internal eMMC writes. Cold boot returns to the untouched stock kernel;
SD extlinux default applies only after operator APX -> RAM U-Boot.
Perform stage, verify, load and execute as separate, explicit operations.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

HOST = "sl101-nura"
CID = "035344534c31323880ac79a543010300"
STOCK = "7.0.1-postmarketos-grate"
CANDIDATE = "7.0.1-postmarketos-grate-dmafix1"
KERNEL_SHA = "315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541"
DTB_SHA = "01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0"
STOCK_SHA = "794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1"
OLD_CONF_SHA = "06082cd3d3efb86bc7a91e81a1127dabb7465dfd0b65753c6b37afc7fff4afaf"
CMDLINE = "root=/dev/mmcblk1p1 rootfstype=ext4 rootwait rw console=tty0 video=tegrafb loglevel=7"
BOOT = Path("/boot")
SOURCE = BOOT / "zImage-k76-dontkmap"
TARGET = BOOT / "zImage-dmafix1-prod-candidate"
DTB = BOOT / "tegra20-asus-sl101.dtb"
CONF = BOOT / "extlinux/extlinux.conf"
STATE = Path("/var/lib/sl101-dmafix1-prod-candidate-20261110")
LOCK = Path("/run/lock/sl101-nura-qualification.lock")
MODULE = Path("/lib/modules") / CANDIDATE
MANIFEST_STAGE = Path("/tmp/sl101-dmafix1-rc2-modules.sha256")
MANIFEST = STATE / "modules.sha256"
BASE_MANIFEST = Path("/tmp/sl101-dmafix1-module-verify.sha256")
BASE_MANIFEST_SHA = "0c96cab49bc5f154a2a5793ab653edcf6f4789ae1a05e7bdc43c974b21977997"
MANIFEST_SHA = "52e096e120a522708069f2fdc460df544df04ac1cf98170a007eecfc2d9f8e7c"
STAGED_VDE = Path("/tmp/sl101-dmafix1-vde-rc2.ko.zst")
VDE_MODULE = MODULE / "kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst"
VDE_OLD_SHA = "1071962fe35550908ae9f02c28596a9321a0bd3c4de5aca1c6ad8f908dc9a96c"
VDE_NEW_SHA = "9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f"
VDE_PATCH_SHA = "d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de"
# The complete self-contained RC is verified and retained on the host.
# The tablet already holds the matching kernel and 587 modules; transfer
# only the missing VDE binary plus full module checksum manifest.
RC_ARCHIVE_SHA = "02c4c66cabef1560765e72a358a225e86ac00f5d75dbe905f288e6faab666912"


class Guard(Exception):
    pass


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise Guard(message)


def atomically(path, data, mode=0o644):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".new.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def updated_conf(old):
    require(hashlib.sha256(old).hexdigest() == OLD_CONF_SHA,
            "original APX extlinux SHA mismatched")
    replacements = (
        (b"default grate-k76-dontkmap", b"default dmafix1-prod-candidate"),
        (b"label grate-k76-dontkmap", b"label dmafix1-prod-candidate"),
        (b"menu label EXPERIMENTAL: SL101 Grate 0076 DONT_KMAP",
         b"menu label PROD-CANDIDATE: SL101 Grate dmafix1"),
        (b"kernel /boot/zImage-k76-dontkmap",
         b"kernel /boot/zImage-dmafix1-prod-candidate"),
        (b"fdt /boot/tegra20-asus-sl101-k76.dtb",
         b"fdt /boot/tegra20-asus-sl101.dtb"),
    )
    result = old
    for previous, replacement in replacements:
        require(result.count(previous) == 1, "APX extlinux expected line missing/ambiguous: " + previous.decode())
        result = result.replace(previous, replacement, 1)
    require(b"label postmarketOS\n" in result, "stock APX fallback entry missing")
    require(b"kernel /vmlinuz\n" in result, "stock APX fallback kernel altered")
    require(b"default dmafix1-prod-candidate\n" in result, "candidate default absent")
    return result


def validate_target(require_stock=True):
    require(os.geteuid() == 0, "root required")
    require(Path("/etc/hostname").read_text().strip() == HOST, "wrong target hostname")
    require(Path("/sys/block/mmcblk1/device/cid").read_text().strip() == CID, "wrong physical SD")
    release = os.uname().release
    require(release in ((STOCK,) if require_stock else (STOCK, CANDIDATE)),
            "unexpected kernel release " + release)
    require(os.stat("/").st_dev == os.stat("/dev/mmcblk1p1").st_rdev,
            "root is not the expected SD partition")
    require(sha(BOOT / "vmlinuz") == STOCK_SHA, "stock cold-boot image drift")
    require(sha(DTB) == DTB_SHA, "DTB drift")
    return release


def require_power():
    require(Path("/sys/class/power_supply/ac-adapter-detect/online").read_text().strip() == "1",
            "external power absent; refusing reboot")


def module_check(base=False):
    require(MODULE.is_dir(), "candidate module root absent")
    count = len(list(MODULE.rglob("*.ko.zst")))
    require(count == 587, f"module count mismatch: {count}")
    expected = VDE_OLD_SHA if base else VDE_NEW_SHA
    require(VDE_MODULE.is_file() and not VDE_MODULE.is_symlink()
            and sha(VDE_MODULE) == expected, "installed VDE module SHA mismatch")
    manifest = BASE_MANIFEST if base else MANIFEST
    expected_manifest_sha = BASE_MANIFEST_SHA if base else MANIFEST_SHA
    require(manifest.is_file() and sha(manifest) == expected_manifest_sha,
            "missing/tampered host-pinned module manifest")
    # GNU and BusyBox both return nonzero on any missing/mismatching file.
    with open(os.devnull, "wb") as null:
        result = subprocess.run(["sha256sum", "-c", str(manifest)],
                                cwd="/", stdout=null, stderr=subprocess.PIPE)
    require(result.returncode == 0, "module SHA256 mismatch: " +
            result.stderr.decode(errors="replace")[:200])


def verify_stage():
    require(SOURCE.is_file() and not SOURCE.is_symlink() and sha(SOURCE) == KERNEL_SHA,
            "staged old-label candidate kernel hash drift")
    require(TARGET.is_file() and not TARGET.is_symlink() and sha(TARGET) == KERNEL_SHA,
            "canonical candidate kernel missing/drifted")
    backup = STATE / "extlinux.before"
    require(backup.is_file() and sha(backup) == OLD_CONF_SHA, "stock extlinux backup missing/drifted")
    expected = updated_conf(backup.read_bytes())
    require(CONF.read_bytes() == expected, "candidate APX default drifted")
    receipt = json.loads((STATE / "receipt.json").read_text())
    require(receipt["candidate_kernel_sha256"] == KERNEL_SHA and
            receipt["original_extlinux_sha256"] == OLD_CONF_SHA and
            receipt["candidate_extlinux_sha256"] == hashlib.sha256(expected).hexdigest(),
            "candidate receipt mismatch")
    require(sha(DTB) == DTB_SHA, "candidate DTB drift")
    module_check()
    require(receipt["vde_module_sha256"] == VDE_NEW_SHA and
            receipt["vde_patch_sha256"] == VDE_PATCH_SHA and
            receipt["complete_candidate_sha256"] == RC_ARCHIVE_SHA,
            "candidate receipt missing VDE patch provenance")
    print("DMAFIX1_APX_DEFAULT_VERIFIED", "image="+KERNEL_SHA,
          "extlinux="+receipt["candidate_extlinux_sha256"])


def stage():
    require_power()
    validate_target()
    require(Path("/sys/kernel/kexec_loaded").read_text().strip() == "0",
            "unrelated kexec already loaded")
    require(sha(SOURCE) == KERNEL_SHA, "candidate source hash mismatch")
    require(sha(DTB) == DTB_SHA, "DTB hash mismatch")
    if STATE.exists():
        verify_stage()
        print("DMAFIX1_ALREADY_STAGED")
        return
    # Before touching any installed file, prove ALL 601 original module
    # tree entries and the exact newly built module payload.
    module_check(base=True)
    require(STAGED_VDE.is_file() and not STAGED_VDE.is_symlink()
            and sha(STAGED_VDE) == VDE_NEW_SHA, "complete RC VDE payload mismatch")
    require(MANIFEST_STAGE.is_file() and sha(MANIFEST_STAGE) == MANIFEST_SHA,
            "complete RC module SHA256 manifest absent or drifted")
    old = CONF.read_bytes()
    new = updated_conf(old)
    require(not TARGET.exists(), "candidate destination already exists without receipt")
    STATE.mkdir(mode=0o700)
    atomically(STATE / "extlinux.before", old, mode=0o600)
    # Persist the signed-off manifest: /tmp can be cleared on reboot.
    atomically(MANIFEST, MANIFEST_STAGE.read_bytes(), mode=0o600)
    require(sha(MANIFEST) == MANIFEST_SHA, "persisted manifest drift")
    atomically(STATE / "tegra-vde.before.ko.zst", VDE_MODULE.read_bytes(), mode=0o600)
    require(sha(STATE / "tegra-vde.before.ko.zst") == VDE_OLD_SHA,
            "VDE original backup not verified")
    atomically(TARGET, SOURCE.read_bytes())
    require(sha(TARGET) == KERNEL_SHA, "copied candidate hash mismatch")
    # Install exact VDE fix into the FULL 587-module tree. On any validation
    # failure restore the prior VDE module and abort before changing extlinux.
    try:
        atomically(VDE_MODULE, STAGED_VDE.read_bytes())
        module_check()
    except Exception:
        atomically(VDE_MODULE, (STATE / "tegra-vde.before.ko.zst").read_bytes())
        raise
    receipt = {
        "schema": "sl101-dmafix1-vde-rc2-nextboot-v1",
        "host": HOST,
        "sd_cid": CID,
        "release": CANDIDATE,
        "candidate_kernel_sha256": KERNEL_SHA,
        "candidate_dtb_sha256": DTB_SHA,
        "vde_module_sha256": VDE_NEW_SHA,
        "vde_patch_sha256": VDE_PATCH_SHA,
        "complete_candidate_sha256": RC_ARCHIVE_SHA,
        "original_extlinux_sha256": OLD_CONF_SHA,
        "candidate_extlinux_sha256": hashlib.sha256(new).hexdigest(),
        "cold_boot_fallback": "untouched internal eMMC stock 7.0.1",
        "apx_default_only": True,
        "kexec_one_shot": True,
    }
    atomically(STATE / "receipt.json",
               (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode(),
               mode=0o600)
    # FINAL mutation: only SD extlinux is edited; stock eMMC untouched.
    require(CONF.read_bytes() == old, "extlinux changed concurrently")
    atomically(CONF, new)
    verify_stage()
    os.sync()
    print("DMAFIX1_APX_DEFAULT_STAGED")


def load():
    require_power()
    validate_target()
    verify_stage()
    module_check()
    require(Path("/sys/kernel/kexec_loaded").read_text().strip() == "0",
            "kexec image already loaded; refusing overwrite")
    require(Path("/proc/cmdline").read_text().strip() == CMDLINE,
            "running root command line does not match candidate")
    result = subprocess.run(
        ["/usr/sbin/kexec", "-l", str(TARGET), "--dtb=" + str(DTB),
         "--command-line=" + CMDLINE], timeout=30, capture_output=True, text=True
    )
    require(result.returncode == 0, "kexec load failed: " + result.stderr[-600:])
    require(Path("/sys/kernel/kexec_loaded").read_text().strip() == "1",
            "kexec load did not set kexec_loaded=1")
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    atomically(STATE / "kexec-loaded", (KERNEL_SHA + " " + boot_id + "\n").encode(), mode=0o600)
    os.sync()
    print("DMAFIX1_KEXEC_LOADED_NOT_EXECUTED", KERNEL_SHA)


def execute():
    require_power()
    validate_target()
    verify_stage()
    require(Path("/sys/kernel/kexec_loaded").read_text().strip() == "1",
            "no loaded kexec candidate")
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require((STATE / "kexec-loaded").read_text().strip() ==
            KERNEL_SHA + " " + boot_id,
            "loaded candidate provenance or boot-ID marker missing")
    print("DMAFIX1_ONE_SHOT_REBOOT_NOW", flush=True)
    os.sync()
    os.execv("/usr/sbin/kexec", ["kexec", "-e"])


def rollback():
    validate_target(require_stock=True)
    require(os.uname().release == STOCK,
            "rollback module restore requires stock running kernel")
    require(STATE.is_dir(), "no candidate receipt/backup")
    verify_stage()
    original = (STATE / "extlinux.before").read_bytes()
    require(hashlib.sha256(original).hexdigest() == OLD_CONF_SHA, "backup hash mismatch")
    atomically(CONF, original)
    require(sha(CONF) == OLD_CONF_SHA, "rollback readback failed")
    # Restore the original VDE module too, but only on stock kernel (a
    # running candidate may be using this module and its dependency indices).
    original_vde = (STATE / "tegra-vde.before.ko.zst").read_bytes()
    require(hashlib.sha256(original_vde).hexdigest() == VDE_OLD_SHA,
            "original VDE module backup mismatch")
    atomically(VDE_MODULE, original_vde)
    require(sha(VDE_MODULE) == VDE_OLD_SHA, "VDE rollback mismatch")
    print("DMAFIX1_APX_DEFAULT_ROLLED_BACK")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("stage", "verify", "load", "execute", "rollback"))
    args = p.parse_args()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Guard("graphics qualification lock held") from exc
        validate_target(require_stock=args.action in ("stage", "load", "execute"))
        if args.action == "stage":
            stage()
        elif args.action == "verify":
            verify_stage()
        elif args.action == "load":
            load()
        elif args.action == "execute":
            execute()
        else:
            rollback()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.TimeoutExpired, Guard) as exc:
        print("DMAFIX1_BOOT_GUARD_FAIL:", exc, file=sys.stderr)
        sys.exit(70)
