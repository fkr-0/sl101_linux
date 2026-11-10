# SL101 dmafix1 + VDE — complete production-candidate RC2

2026-11-10. Target: **only** `sl101-nura` at `192.168.23.106`, SD CID
`035344534c31323880ac79a543010300`. Boot release:
`7.0.1-postmarketos-grate-dmafix1`. This is **not** the K76 debug kernel
or Debian/GLIBC tablet.

## Current patchset, binary provenance

The original `dmafix1` archive is **not** a complete RC, because it does
not contain the VDE worker-thread synchronization fix. RC2 supersedes it.

RC2 packages **both** source patches and the matching compiled code:

1. `patches/0002-dma-direct-zero-no-kmap.patch`, SHA-256
   `b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b`.
   Included in the productive 7.0.1-derived zImage, SHA-256
   `315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541`.
2. `patches/0003-tegra-vde-async-semaphore.patch`, SHA-256
   `d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de`.
   The affected VDE driver is **a loadable module**. Its patch was
   compiled against the exact `dmafix1` `.config` and
   `Module.symvers`, and replaces the module inside the complete
   release tree at `kernel/drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko.zst`.
   Module SHA-256 `9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f`.

The module's vermagic equals the kernel release; dependency and alias
interfaces match the original. `depmod` was re-run over all 587 modules;
its regenerated `modules.*` files are **byte-identical** to the original
complete module tree. Every file (608 entries) is checksummed. Both
patches are included in the package; the unrelated CMA alias hypothesis
patch remains excluded.

Complete portable archive:
`work/sl101-dmafix1-vde-rc2-20261110/sl101-dmafix1-vde-rc2-complete.tar.zst`

Archive SHA-256:
`02c4c66cabef1560765e72a358a225e86ac00f5d75dbe905f288e6faab666912`.

Rebuild/verification (host, no device mutations):

    python3 scripts/sl101-prod-dmafix1-candidate.py
    python3 scripts/sl101-prod-dmafix1-vde-rc.py
    python3 -m unittest discover -s tests -p test_sl101_prod_dmafix1_vde_rc_20261110.py -v
    python3 -m unittest discover -s tests -p test_sl101_dmafix1_prod_candidate_boot_20261110.py -v

## Boot model and recovery

The tablet's cold boot **does not** interpret
`/boot/extlinux/extlinux.conf`; that SD file applies only when a user
enters APX and loads the verified RAM-only U-Boot. Therefore the next
reboot is an explicit one-shot **`kexec -l` + `kexec -e`** from the
running stock kernel, with the same root and DTB. The SD extlinux
`default` is changed to the complete RC as the default for a later
operator APX boot. The internal eMMC boot image and all permanent
bootloader bytes stay untouched. A physical cold boot returns to the
original stock kernel if the candidate fails.

The isolated helper `scripts/sl101-dmafix1-prod-candidate-boot.py`
is guarded by hostname, SD CID, expected stock version, exact base image,
AC power, whole module manifest, single graphics qualification lock,
the host-verified RC archive hash recorded in its receipt, and the known
original extlinux hash. The immutable 20-MiB complete RC archive remains
on the host; since the tablet already has the hash-matched kernel and
587-module baseline, only the missing 31-KiB patched VDE module and
updated whole-tree checksum manifest are transferred over fragile WLAN.
The device independently verifies the kernel hash, the new VDE hash and
the checksums of every installed module/metadata file. It backs up
the original extlinux and VDE module, installs the patched VDE module,
verifies the entire updated module tree, and only **then** atomically
updates SD extlinux. `verify`, `load`, `execute` are separate
actions; `execute` requires a confirmed loaded candidate marker.
The host-pinned, 601-entry on-device module checksum index is copied into
the root-owned state directory before mutation so it survives reboot.
The one-shot kexec marker also contains the current boot ID.

A rollback helper restores the prior SD default and prior VDE module,
including when staging was interrupted before writing its receipt. It
runs only on the stock kernel, refuses unknown states or pending kexec,
and preserves evidence in a distinct `.rolledback-<boot-id>` directory.

After reboot, confirm exact release, VDE module SHA, boot command line,
active kernel logs, Wi-Fi/SSH, EC modules, LVDS/Grate, Sway/WayVNC and
input without unsafe suspend tests. Current RC2 VDE behavior has NOT
yet passed hardware video/decoder testing: the first boot validates
basics; acceptance of VDE/KMS video remains its own gate.

## Actual supervised .106 rollout (2026-11-10)

**Verified directly before handoff:**

- Target: `sl101-nura`, SD CID `035344534c31323880ac79a543010300`,
  running stock `7.0.1-postmarketos-grate`, external AC online.
- Full original 601-entry module manifest verified; after installing the
  current VDE fix, the complete RC2 manifest passed and patched VDE module
  SHA-256 was `9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f`.
- SD/APX extlinux default atomically changed to `dmafix1-prod-candidate`;
  extlinux SHA-256 `17e3b857376c8610f036110024a6d6f05592fd6ac6280c218106e5e8d632b13d`.
- Original extlinux and VDE module preserved under
  `/var/lib/sl101-dmafix1-prod-candidate-20261110/`:
  SHA-256 `06082cd3d3efb86bc7a91e81a1127dabb7465dfd0b65753c6b37afc7fff4afaf`
  and `1071962fe35550908ae9f02c28596a9321a0bd3c4de5aca1c6ad8f908dc9a96c`.
- One-shot `kexec -l` succeeded, `kexec_loaded=1`. Root-owned marker
  records image SHA `315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541`
  and boot ID `d1f3ff6d-e125-425a-b6b1-3021091906fc`.
- Explicitly authorized `execute` reverified the full module tree and
  emitted `DMAFIX1_ONE_SHOT_REBOOT_NOW` immediately before `kexec -e`.

**Postboot not yet confirmed:** SSH timed out and ARP/ping did not answer
immediately after handoff. This proves the handoff was issued, NOT that
the candidate finished booting. No postboot VDE/KMS or Cog test was
performed. With physical access, a cold power cycle returns via the
unchanged internal stock boot path if the candidate hangs. Do not blindly
retry kexec or rewrite eMMC.
