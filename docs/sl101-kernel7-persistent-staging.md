# SL101 Nura 7.x persistent staging — one-shot fail-back design

## Purpose

This procedure stages the canonical Nura kernel 7.0.1-postmarketos-grate
without replacing the SL101's known internal 6.18 cold-boot path.

Observed boot model:

    power-on
      -> internal Android-header 6.18.45 kernel
      -> Nura root on /dev/mmcblk1p1
      -> optional one-shot kexec handoff
      -> canonical 7.0.1-postmarketos-grate

If the 7.x handoff fails, a physical power-cycle returns to the internal 6.18
path. No eMMC boot image, bootloader, partition table or raw boot slot is changed
by this staging design.

## Host bundle

Build and verify:

    python scripts/sl101-kernel7-oneshot.py build \
      --source-root tmp/sl101-nura/work/chroot_rootfs_nvidia-tegra-armv7 \
      --provenance tmp/sl101-nura/kernel7-consolidation/provenance.json \
      --out tmp/sl101-nura/kernel7-persistent-stage

    python scripts/sl101-kernel7-oneshot.py verify \
      --bundle tmp/sl101-nura/kernel7-persistent-stage

Current bundle invariants:

    target release       7.0.1-postmarketos-grate
    recovery release     6.18.45
    root device          /dev/mmcblk1p1
    module count         587
    service auto-enabled false
    marker               /var/lib/sl101-kernel7/nextboot

The bundle contains:

    /opt/nura-kernel7/vmlinuz
    /opt/nura-kernel7/tegra20-asus-sl101.dtb
    /opt/nura-kernel7/config
    /opt/nura-kernel7/modules.sha256
    /opt/nura-kernel7/manifest.json

    /lib/modules/7.0.1-postmarketos-grate/...

    /usr/local/sbin/sl101-kernel7-oneshot
    /etc/init.d/sl101-kernel7-oneshot

It intentionally does not contain:

    /etc/runlevels/default/sl101-kernel7-oneshot

Enabling the OpenRC service is a separate human-present step.

## Exact boot artifacts

The helper accepts only the canonical hashes:

    vmlinuz
    794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1

    SL101 DTB
    01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0

    config
    6b09863a5f4356ce615f7d5d4cdecbba4cd2cc208c34125954af9534648f9248

Every file in the matching module tree is checked against
/opt/nura-kernel7/modules.sha256 before kexec is loaded.

The target command line is the root-on-partition-1 contract already used during
the successful RAM-only Grate tests:

    root=/dev/mmcblk1p1 rootfstype=ext4 rootwait rw
    console=tty0 video=tegrafb loglevel=7

## One-shot behavior

The generated runtime helper is fail-back by construction.

No marker:

    /var/lib/sl101-kernel7/nextboot absent
      -> helper exits 0
      -> remain on 6.18 recovery kernel

Marker present:

1. atomically move /var/lib/sl101-kernel7/nextboot to
   /var/lib/sl101-kernel7/pending;
2. wait ten seconds by default, allowing a physically-present or remote operator
   to cancel by removing pending;
3. recheck pending;
4. move pending into
   /var/lib/sl101-kernel7/consumed/<boot-id>-<timestamp>;
5. only then run preflight;
6. verify current kernel is exactly 6.18.45;
7. verify root is exactly /dev/mmcblk1p1;
8. verify kernel, DTB and config hashes;
9. verify the complete 7.x module tree;
10. load the exact 7.x kernel/DTB with kexec -l;
11. execute with kexec -e.

The retry-capable nextboot marker is consumed before the grace period. A power
loss during that grace therefore leaves only pending; the following cold boot
has no nextboot marker and cannot retry automatically.

A fresh marker is required for every new attempt. An old pending file is kept as
evidence until an operator explicitly requests another attempt; the helper then
archives it under consumed before consuming the new marker.

## Host test coverage

tests/test_sl101_kernel7_oneshot.py covers:

- bundle build + verification;
- module count and no automatic OpenRC enablement;
- nextboot consumption appears before the grace sleep;
- pending consumption appears before kexec -l;
- missing marker -> no action;
- wrong recovery kernel -> fail closed;
- wrong root device -> fail closed;
- kernel hash mismatch -> fail closed;
- DTB hash mismatch -> fail closed;
- config hash mismatch -> fail closed;
- module tree mismatch -> fail closed;
- tampered bundle artifact -> verification failure;
- correct preflight -> ready-for-one-shot result.

These are host/fixture tests. They do not themselves qualify the physical boot.

## Human-present staging procedure

Do not perform this procedure unattended.

Before copying anything, verify:

1. tablet is physically present;
2. cold-boot recovery path currently works;
3. current root device is /dev/mmcblk1p1;
4. battery/power are adequate;
5. exact canonical bundle verifies on the host;
6. no concurrent GPU/compositor qualification owns the tablet lock.

Then copy the bundle paths into the corresponding paths on the Nura rootfs.
Do not write eMMC boot slots or U-Boot.

After copy, verify the on-device files against the host bundle before enabling
anything.

Enable the service explicitly:

    rc-update add sl101-kernel7-oneshot default

The service is harmless without a marker.

## Request exactly one candidate boot

With a human present:

    mkdir -p /var/lib/sl101-kernel7
    : > /var/lib/sl101-kernel7/nextboot
    sync

Then perform an ordinary reboot/power-cycle into the known 6.18 recovery path.

During the ten-second grace period, nextboot has already been consumed. To
cancel the handoff, remove:

    /var/lib/sl101-kernel7/pending

If not cancelled, pending is archived under consumed and the helper attempts
one 7.x kexec.

If power is lost during the grace period, pending may remain on disk, but there
is no nextboot marker. The following 6.18 cold boot therefore does not retry.

## First 7.x boot acceptance

Immediately after the tablet returns, establish:

    uname -r == 7.0.1-postmarketos-grate

Then verify:

1. exact boot image/DTB provenance is the canonical set;
2. /lib/modules/7.0.1-postmarketos-grate is present;
3. kernel coherence gate passes;
4. no EC/KBC duplicate-symbol or duplicate-driver messages;
5. EC identifies ASUS-EP102-DOCK / SL101-0202;
6. slider keyboard produces input;
7. touchscreen works;
8. backlight/display work;
9. Wi-Fi associates and SSH returns;
10. zram service/device state matches the 7.x config;
11. nftables initializes;
12. labwc starts using pixman;
13. NuraLoumi panel/menu start;
14. no unexpected kernel fault/reset appears.

Do not start GPU/EGL qualification until this base runtime passes.

Do not test deep suspend in this phase.

## Natural rollback

If the 7.x handoff fails:

1. physically power-cycle the tablet;
2. internal 6.18 cold boot runs again;
3. nextboot has already been consumed, so the service does not retry;
4. inspect /var/lib/sl101-kernel7/pending,
   /var/lib/sl101-kernel7/consumed/ and
   /var/lib/sl101-kernel7/last-error;
5. fix the cause;
6. create a new marker only for an explicitly approved second attempt.

No raw boot restoration is required because this mechanism never replaces the
internal boot image.

## Disable the bridge

After the canonical 7.x boot path has another persistent solution, or whenever
the bridge is not wanted:

    rm -f /var/lib/sl101-kernel7/nextboot
    rm -f /var/lib/sl101-kernel7/pending
    rc-update del sl101-kernel7-oneshot default

Removing the staged files is optional after the service is disabled; their
presence alone cannot trigger a kexec.

## Promotion rule

This one-shot bridge is a qualification mechanism, not the final boot
architecture.

Only after repeated clean 7.x boots, physical input/network checks, shallow
resume qualification and a reviewed recovery procedure should we consider
changing the persistent boot architecture itself.
