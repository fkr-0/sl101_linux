# SL101 — Two physical boot chains, ONE shared DMA+VDE production kernel

Date: 2026-11-10. This is the **canonical current operator/device mapping**.
The prior inference that the Nura device always returns to the ASUS stock
bootloader after a cold reboot is **unproven and must not be used to plan
deployment or recovery**.

## Physical topology verified by read-only SSH on BOTH devices

| Field | .100 | .106 |
| --- | --- | --- |
| SSH/hostname | user@192.168.23.100 / sltwrpbootdebian | user@192.168.23.106 / sl101-nura |
| Distribution | Debian 13, glibc | Nura/postmarketOS Alpine, musl |
| Bootloader | Original ASUS/Android bootloader, RootBind-style LNX kernel boot | Native U-Boot in internal eMMC (owner's device identification and project notes) |
| Kernel installation route | ASUS LNX Android-header 8-MiB eMMC slot | U-Boot kernel + DTB; actual selected kernel file still to be demonstrated |
| Internal eMMC | mmcblk0; CID 7001004d4d43333247447e682c336e00 | mmcblk0; CID 7001004d4d43333247448d402a656e00 |
| External microSD | mmcblk1; CID 03534453553332478030be3f6400b900 | mmcblk1; CID 035344534c31323880ac79a543010300 |
| Running Linux root | microSD /dev/mmcblk1p1 (ext4) | microSD /dev/mmcblk1p1 (ext4) |
| Current running kernel | 7.0.1-postmarketos-grate | 7.0.1-postmarketos-grate |
| SD /boot/extlinux default | Debian-EC-current | dmafix1-prod-candidate, NOT the active kernel |

Important: U-Boot or ASUS bootloader **on eMMC** is not the same as the
root filesystem **on eMMC**. Kernel command line, findmnt, MMC device types,
CIDs and root source currently establish **microSD root on both tablets**.
The .106 permanent/native U-Boot bootloader is an operator identity plus
historical project evidence, but Linux shell state alone does not prove
the U-Boot search path or currently loaded kernel image source.

Both observed running kernel configurations from /proc/config.gz have
identical SHA-256:
6b09863a5f4356ce615f7d5d4cdecbba4cd2cc208c34125954af9534648f9248.

### What the .106 reboot actually establishes

The SD file /boot/extlinux/extlinux.conf has
default dmafix1-prod-candidate; the staged kernel exists at
/boot/zImage-dmafix1-prod-candidate (SHA-256
315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541).
The staged VDE module exists under the dmafix1 module tree (SHA-256
9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f).
Nevertheless the **running** kernel after the operator's cold reboot is
7.0.1-postmarketos-grate and /boot/vmlinuz has SHA-256
794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1.
The old stock kernel was loaded; this does **not** prove the candidate
kernel is buggy or even that U-Boot consulted the edited SD extlinux file.
The earlier kexec timeout was not a proven panic. Determine the current
U-Boot bootmethod and actual kernel source using console/boot-environment
evidence before touching the persistent default. Do not assume that a
successful file write to SD extlinux changes the real native-U-Boot default.

Earlier statements in docs/sl101-dmafix1-prod-candidate-boot-20261110.md
about a universal .106 vendor-stock cold-boot recovery path were
overconfident and are superseded by this document.

### How .100 boots

The ASUS bootloader is intentionally preserved. Debian is RootBind-style
in the sense that the normal ASUS LNX boot slot contains a Linux kernel
boot image; unlike historical RootBind the root filesystem is on microSD,
NOT /data/linuxroot. A physically supervised 8-MiB LNX write/readback was
documented on November 9 in docs/sl101-asus-apx-free-boot-20261109.md.
Its absolute eMMC LNX slot starts at **8,912,896**, length **8,388,608**
bytes. Never write the historical 14-MiB LNX+BAK+GP1 composite; leave
BCT, EBT, SOS, BAK, GP1 and Android data unchanged. The Debian
SD /boot/extlinux.conf is not by itself proof of what ASUS LNX boots.

## Target release: ONE kernel source + modules, TWO boot packages

Decision: both tablets must receive the SAME productive 7.0.1-r4-derived
kernel image and matching 587-module ABI tree. The different libc/OS
does not require a different kernel. Exact board-compatible DTBs and boot
containers still need individual verification.

Two **required fixes** were demonstrated/implemented:

1. DMA_DIRECT_NO_KERNEL_MAPPING zero initialization with non-coherent DMA
   synchronization, repairing the fresh-buffer rendering artifacts:
   patches/linux-postmarketos-grate-7.0.1/dmafix1/0002-dma-direct-zero-no-kmap.patch
   SHA-256 b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b.
   Prior on-device DMAfix results: 216/216 + 108/108 clean.
2. Tegra VDE async decode worker mutex-owner repair, replacing a
   task-owned mutex across threads with an ownerless semaphore:
   patches/linux-postmarketos-grate-7.0.1/vde-modfix2/0001-media-tegra-vde-async-semaphore.patch
   SHA-256 d93fc2f5924005a8f1abbe902df3ecbe753614f5dc520840c1d2b6e48e23e0de.
   Tegra-VDE is a **loadable kernel module**, not a second zImage.
   Its module must be compiled against the exact kernel config and
   Module.symvers with matching vermagic and release name.

The combined, two-functional-fix RC2 already exists:
  tag: sl101-kernel-dmafix1-vde-rc2-20261110
  release: 7.0.1-postmarketos-grate-dmafix1
  archive: work/sl101-dmafix1-vde-rc2-20261110/sl101-dmafix1-vde-rc2-complete.tar.zst
  archive SHA256: 02c4c66cabef1560765e72a358a225e86ac00f5d75dbe905f288e6faab666912
  zImage SHA256: 315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541
  VDE module SHA256: 9996fee6495a93374c4cf92f0ec942debae29b872d2429f07e35e63604531f4f

This package is complete and host verified, but has not yet been
confirmed after a cold boot on either device.

## Do not mistake RC3 for mandatory production changes

There is a newer host-built development candidate
7.0.1-postmarketos-grate-dmavde1, see
docs/sl101-kernel-dmavde-rc3-20261110.md. It contains the two required
patches **plus** (a) an *experimental, not yet hardware-qualified*
generic ARM/CMA lowmem alias remap and (b) a cached VDE CAPTURE path
default OFF, separately qualified earlier as a VDE module.
RC3 has 587 matching modules but no joint device qualification.
It should NOT silently replace RC2 just because it has more patches.
The cached CAPTURE optimization may be separately qualified as a
future optional addition; generic CMA remapping requires its own
evidence. A final product release needs explicit source-patch freeze.

## Packaging / qualification, not yet performed

- .100: wrap the shared kernel in the **exact ASUS Android-header
  8-MiB LNX slot** (with correct DTB and bootargs), preserve current
  original 8-MiB LNX and adjacent partition hashes, stage matching
  modules on Debian SD, confirm physical APX recovery first.
- .106: preserve permanent eMMC U-Boot, discover the actually consulted
  boot menu / extlinux / boot.scr / eMMC kernel target, stage the same
  kernel/compatible DTB there with a selectable recovery, stage matching
  modules on Nura SD. Editing /boot/extlinux alone is insufficient proof.
- On **each** tablet after an explicitly authorized boot, compare
  uname -r, running config, DTB, VDE vermagic/CRC/module SHA and the
  full module manifest; validate Wi-Fi, EC, input, video, Sway/WayVNC
  where applicable and fresh BO/dma rendering pixels; verify absence
  of the cross-owner VDE mutex warning under bounded H.264 decode.
- Repeat a normal power-on cold boot on **both** independently; only
  then promote from candidate to production.

No flashes, boot default changes, reboots, kexec or media workloads
were performed while writing this reconciliation.
