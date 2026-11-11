# Debian SL101 .100 — four-patch CMA kernel staged; FLASH BLOCKED BY POWER

Date: 2026-11-11. Device sltwrpbootdebian, 192.168.23.100.

**Status: kernel, DTB, 587 modules and physically checked LNX plan are
prepared on SD root; original eMMC LNX is UNCHANGED and no reboot occurred.**

## Physical identity and unchanged stock kernel

- Device hostname: sltwrpbootdebian.
- eMMC CID /dev/mmcblk0: 7001004d4d43333247447e682c336e00.
- microSD CID /dev/mmcblk1: 03534453553332478030be3f6400b900.
- Root filesystem: /dev/mmcblk1p1.
- Running stock kernel: 7.0.1-postmarketos-grate.
- Boot ID when staged: 00eff3d3-b8fd-454f-8596-b333c8592515.
- Original zImage SHA-256: 794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1.
- Original DTB SHA-256: 01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0.
- Original 8-MiB eMMC LNX SHA-256 (checked again before leaving):
  faa6ded4fcda894a7d2174da0ea76d5a6518201ab3c1dd49b9e7ab56cf24e71b.

Host rollback backup, exactly 8,388,608 bytes, under:

    work/sl101-100-dmavde1-deploy-20261111/sl101-100-original-LNX-8MiB-predeploy.img

The physical ASUS eMMC LNX region is at offset 8,912,896 and size
8,388,608. A read-only rawboot plan verified correct stock zImage, DTB,
and target fit. Saved to:

    work/sl101-100-dmavde1-deploy-20261111/read-only-cma-flash-plan.json

The plan was derived against the current stock slot. Its confirmation
token must be **recomputed if any device state changes**, not replayed
blindly. Preserve the ASUS bootloader, BCT, EBT, SOS, BAK, GP1, Android
user data and exact physical device identity.

## Target artifact staged on the Debian SD filesystem

- Human candidate: 7.0.1-pmos-grate-dmavde1.
- Kernel release/ABI: 7.0.1-postmarketos-grate-dmavde1.
- Target zImage SHA-256:
  79911fc494207ff0607373ceed2ff848e8b6b9252e97599a0e75913965e941aa.
- Target DTB SHA-256:
  01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0.
- Target VDE module SHA-256:
  625bc023d0df8903f6387b9ff1c7963ed4ebb79eb3a13c8c1884b6ef4fd7b892.
- Root-private kernel/DTB/guarded flasher directory:

    /var/lib/sl101-kernel-candidates/dmavde1/boot/

- Portable gzip module archive SHA-256:
  c5300a79e3b9d9e339c0bb8a0b6308ab8a4225ceb5a824f04f01d2e5a00ff9df.
- Verified: 587 installed module files and depmod -a for the exact
  new ABI; stock release module tree left untouched.

Module directory:

    /lib/modules/7.0.1-postmarketos-grate-dmavde1

Root-private retained module tar:

    /var/lib/sl101-kernel-candidates/dmavde1/modules.tar.gz

Debian SD /boot/extlinux.conf continues to default to
Debian-EC-current. This SD menu does NOT select the original ASUS
normal eMMC-LNX boot image; editing it would not deploy the kernel.

## Power safety gate — NOT MET

Although AC sensor online=1, the actual battery reported:

- 23%, status Discharging, current -155000 microampere;
- later 22%, status Discharging, current -155000 microampere;
- remaining charge dropped from 451000 to 430000 microampere-hours;
- voltage declined from about 10.98 to 10.95 volts.

This is an **actively discharging tablet despite AC online**. An
uninterrupted flash is short, but a failed boot or APX rescue can
require sustained power. Under these observed conditions it would
not be responsible to rewrite persistent eMMC and reboot remotely.
Therefore: **NO eMMC WRITE; NO REBOOT on .100** in this session.

## Safe completion after restoring charging

1. Make .100 show a genuinely charging or otherwise robust power
   state, preferably battery above 50%; verify again using actual
   capacity, status, current_now, charge_now and AC online.
2. Re-authenticate device hostname, both physical CIDs and original
   full 8-MiB LNX SHA; inspect current running kernel and boot ID.
3. Confirm all 587 modules and new zImage/DTB SHA; retain host
   backup, and have a physically available APX rescue.
4. Generate a NEW sl101-rawboot.py v2 plan from current LNX; use
   its actual content-derived confirmation token.
5. Write only the 8-MiB LNX region with a new, independent
   on-device backup; read back zImage and DTB, compare SOS/BAK/GP1
   hashes, sync, then reboot and confirm a new boot ID + exact kernel.
6. Verify working Debian root, SSH, VDE/DRM and kernel warnings.

**No partial LNX write occurred.** The user can resume this staged
deployment once battery/power is appropriate without rebuilding.
