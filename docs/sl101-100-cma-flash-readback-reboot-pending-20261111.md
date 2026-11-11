# Debian SL101 .100 — four-patch CMA eMMC flash verified; reboot pending

**Date:** 2026-11-11, 09:28–09:32 CET. **Device:** sltwrpbootdebian,
192.168.23.100. **Result: eMMC kernel flash SUCCESSFUL, full physical
readback and neighboring partition validation SUCCESSFUL. Normal reboot
NOT performed: remote restart was blocked by an execution safety gate.
The currently running kernel is STILL stock until a manual reboot.**

## Power recovery and exact target

Following the user's report that power was connected, actual physical
power changed from 22–23% Discharging / -155mA despite AC online to:

- AC online = 1;
- battery status **Charging**;
- battery 58%, 59%, then **60%**;
- current **+908,000 → +907,000 → +906,000 microamps**;
- battery increased rather than declined.

Guards used before writing required actual Charging, battery >= 50%,
current > +200,000 microamps, AC online, correct device, unchanged
stock kernel and boot ID.

Device identity before and after:
- hostname sltwrpbootdebian
- eMMC CID 7001004d4d43333247447e682c336e00 (/dev/mmcblk0)
- microSD CID 03534453553332478030be3f6400b900 (/dev/mmcblk1)
- root filesystem /dev/mmcblk1p1
- original kernel 7.0.1-postmarketos-grate
- original/current pre-reboot boot ID 99aa22e5-432b-4ad8-b789-042d6fedf1c5

## Actual flash and checksums

The known-good ASUS Android-header kernel container is the physical
8,388,608-byte LNX eMMC region at byte offset **8,912,896**.
The repository's guarded device-local sl101-rawboot.py v2 was used
with a live derived content token, after independently matching the
exact old stock image, current DTB, target zImage, target DTB, matching
587 modules and correct VDE module ABI. It backed up the entire
original slot before writing. The kernel+DTB+header occupied only
6,552,646 bytes, within the LNX slot.

Original **stock 8-MiB LNX** SHA-256:
faa6ded4fcda894a7d2174da0ea76d5a6518201ab3c1dd49b9e7ab56cf24e71b.

Independently retained host stock backup (8,388,608 bytes):

    work/sl101-100-dmavde1-deploy-20261111/sl101-100-original-LNX-8MiB-predeploy.img

**Additional exact on-device stock rollback backup:**

    /var/lib/sl101-kernel-candidates/dmavde1/preflash-100-stock-backup/slot-backup.bin
    /var/lib/sl101-kernel-candidates/dmavde1/preflash-100-stock-backup/slot-backup.json

Backup SHA after writing verified equal to the original stock hash.

**New full physical 8-MiB LNX SHA-256:**

    33c5d8194c09c4b92d48258e154eee51327ad997f1b78585dfdc42da17cb4cb2

The on-device full-slot readback after writing confirmed the same new
LNX hash. The boot-image inspector independently confirmed:
- target zImage SHA-256:
  79911fc494207ff0607373ceed2ff848e8b6b9252e97599a0e75913965e941aa
- target SL101 DTB SHA-256:
  01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0
- target release/module ABI:
  7.0.1-postmarketos-grate-dmavde1
- 587/587 matching modules installed on the Debian microSD root,
  including VDE .ko.zst SHA-256
  625bc023d0df8903f6387b9ff1c7963ed4ebb79eb3a13c8c1884b6ef4fd7b892.

On-device verification receipts:

    /var/lib/sl101-kernel-candidates/dmavde1/preflash-plan-live.json
    /var/lib/sl101-kernel-candidates/dmavde1/flash-result.json
    /var/lib/sl101-kernel-candidates/dmavde1/postflash-inspect.json

The neighboring eMMC partitions were SHA-256 checked before and
after the write, **with no changes**:

| eMMC slot | Identical before/after SHA-256 |
| --- | --- |
| SOS | 670a88bdb12269e4a513606e584d1f4f6bbfb9ebfa7c7f88c7883d9c9b302d6c |
| BAK | a10cd12ebac12e18a6859cffdb1c301b7d59782997cd49357797592058ce69da |
| GP1 | 5b4b7174683bb5481e1ed375cd91721f86c069aac029119d2bcde711d4b94e8f |

No BCT, EBT, Android user data, partition table or device .106 writes.

## NEXT: reboot and post-boot qualification, not yet done

After the successful flash/readback, remote execution of the reboot
was **blocked by the tool execution safety policy**; it was not issued
and no attempt was made to bypass this restriction. A subsequent
authenticated, READ-ONLY SSH check confirmed that .100 remains online
with running **stock** kernel 7.0.1-postmarketos-grate, original
pre-reboot boot ID, and charging battery **60%, +906mA**.
The eMMC LNX remained at the *new* SHA, and on-device stock backup
still matched the old SHA.

**A local manual normal reboot is needed, with physical rescue available.**
After it returns, a separate authenticated check should require:

- **a new boot ID** compared with
  99aa22e5-432b-4ad8-b789-042d6fedf1c5;
- uname -r exactly 7.0.1-postmarketos-grate-dmavde1;
- both unchanged physical CIDs, /dev/mmcblk1p1 root, 587 modules;
- VDE /dev/video0, DRM /dev/dri, normal Debian and network service;
- dmesg comparison for DMA/CMA/VDE faults and the pre-existing WM8903
  codec warning.

**Do not report Debian .100 as boot-qualified or production accepted
until those checks pass.** If boot fails, physically supervised
APX/RCM recovery and restoration of this exact stock 8-MiB LNX
backup is possible via scripts/sl101-rawboot.py, after re-verifying
both CIDs, the full-slot hash and backup. Never write the 14-MiB
LNX+BAK+GP1 aggregate; never restore .106's backup to .100.

The .106 tablet was not touched: it remains on the independent
7.0.1-postmarketos-grate-dmavde1-minus-cma benchmark control.
The full CMA/minus-CMA A1–B–A2 performance assessment remains open.
