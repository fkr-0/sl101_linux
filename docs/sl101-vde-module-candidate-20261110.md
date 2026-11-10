# SL101 VDE mutex-owner fix, isolated `dmafix1` module candidate

2026-11-10 — **host-built only; NOT deployed or approved for production video**.

## Scope and exact base

* Kernel: `7.0.1-postmarketos-grate-dmafix1`, derived from **archived
  production** `linux-postmarketos-grate-7.0.1-r4`, not K76.
* Existing kernel zImage SHA-256:
  `315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541`.
* Existing original VDE kernel module SHA-256:
  `1071962fe35550908ae9f02c28596a9321a0bd3c4de5aca1c6ad8f908dc9a96c`.
* Source archive: pinned by the original `APKBUILD` SHA-512, source tree
  originally corresponding to commit `bfffc6d6656e87f3de3aa4c09d852849081ef088`.
  Exact `dmafix1` direct-DMA patch is applied to source first.
* VDE patch:
  `patches/linux-postmarketos-grate-7.0.1/vde-modfix2/0001-media-tegra-vde-async-semaphore.patch`
  SHA-256 `d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de`.
  The patch was dry-run applied without fuzz or rejection to the exact
  archived production source and then applied and compiled off-device.

## Cause and repair boundary

The stock VDE decoder starts work in the V4L2 scheduling task and finishes
in `tegra_decode_complete` on a worker thread. A Linux `mutex` must not be
unlocked by a different task. Direct VDE→KMS 17.25-second video reached EOS,
but emitted `DEBUG_LOCKS_WARN_ON(__owner_task(owner) != get_current())`.
The patch uses a cross-task ownerless binary semaphore for the relevant
asynchronous decode/suspend lock, retaining separate internal map mutexes
and restoring the token on failed suspend.

This avoids a prohibited mutex ownership transfer, **but no claim is made
about its actual runtime warning rate, decode correctness, recoverability,
wake/suspend, buffer recycling or deadlock freedom** until dedicated device
tests. The earlier media warning is documented in
`debian-rootbind/VIDEO-VDE-KMS-20261109.md`.

## Host build result

`scripts/sl101-vde-module-build-20261110.sh` copied the **existing
kernel build output** to a separate ignored lane and extracted pristine
source to a new temporary directory, verified the exact SHA-512, applied
the DMA and VDE patches, and compiled only
`M=drivers/media/platform/nvidia/tegra-vde`, using the original
dmafix1 `.config` and `Module.symvers`. It did **not** alter the
existing `dmafix1` zImage, module tree, source archive, or production devices.

Build result:

* `work/sl101-vde-modfix2-20261110/stage/lib/modules/7.0.1-postmarketos-grate-dmafix1/updates/tegra-vde.ko.zst`
* SHA-256:
  `9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f`.
* `modinfo -F vermagic` =
  `7.0.1-postmarketos-grate-dmafix1 SMP mod_unload modversions ARMv7 p2v8`
  (trailing whitespace omitted).
* Module differs from the original VDE module; exact source patch SHA
  matches the archived candidate. `make modules_install` completed.
* Isolated install warned that depmod could not find the complete
  module inventory (`modules.builtin` and `modules.builtin.modinfo`):
  expected because this **optional overlay** contains only tegra-vde.
  Never use its generated `modules.dep` as a replacement for the full
  dmafix1 module tree. Run `depmod` against the complete target tree
  after any explicitly authorized install.

Run on host (only if lane output does not yet exist):

    bash -n scripts/sl101-vde-module-build-20261110.sh
    bash scripts/sl101-vde-module-build-20261110.sh
    python3 -m unittest discover -s tests -p test_sl101_vde_module_prod_20261110.py -v

## Exact target staging / rollback gate (NOT executed)

1. Require authenticated SSH, physical tablet recovery and exclusive
   graphics qualification lock. Confirm hostname/CID/boot ID, active
   `uname -r`, loaded `tegra_vde` and exact original module SHA.
2. Use the full `dmafix1` boot and module base. Back up original
   `tegra-vde.ko.zst` *and* `modules.dep{,.bin}`, plus dmesg before/after.
   Stage the candidate under a distinct `updates/` directory, not over
   the original module. Verify sha and `modinfo` before registering it.
3. Stop all VDE clients with their actual process identity; never unload
   an active module. Rebuild dependency indices for the **full** installed
   module tree, verify `modprobe --show-depends tegra_vde` chooses the
   candidate, then load it only during supervised tests.
4. First run decoder-only bounded test, inspect decoded frames against a
   software reference, then *separately* direct KMS DMA-Buf playback.
   Require zero mutex owner warning, zero other kernel faults, correct
   output pixels, expected frame progress and reliable Sway restore.
5. For the Wayland/Sway route independently test correct three-plane YUV
   import, Grate EGl mapping and scanout. Don't conflate KMS DMA-Buf
   success with GPU-composited video under Sway.
6. On any warning/error, unload only when safe, remove candidate overlay,
   regenerate depmod from original full modules, reload original module,
   restore the desktop/graphics owner and preserve logs. A power-cycle
   restores the stock boot chain only according to its verified APX/U-Boot
   route; do not assume permanent bootloader installation.

After hardware qualification a dedicated follow-up may integrate this
module or exact patch into a newly versioned whole kernel package.
**Current production baseline remains `dmafix1` without the overlay.**
