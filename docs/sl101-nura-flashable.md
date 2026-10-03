# SL101 ad hoc Nura SD setup

This is a private recovery snapshot of the working SL101 installation, not an
upstream device release. Output lives in `tmp/sl101-nura/flashable/` with private
permissions. It retains Wi-Fi credentials, SSH keys and the existing host
identity: do not publish it or run two copies on the same network unchanged.

## Boot contract

The tested tablet cold-boots its **internal 6.18.45 Android-header kernel** with
`root=/dev/mmcblk1p1 rootfstype=ext4 rootwait`. The image therefore has an MBR and
one ext4 partition starting at sector 2048, with root UUID
`6dd3675d-b5cf-41bd-9262-103c59321451`. It includes matching 6.18.45 modules.
The SD `/boot/extlinux` entry does not establish which kernel this tablet loads.
This image alone does not provision a stock SL101's internal boot path.

The 7.0.1 Grate kernel and its modules remain available for manual RAM-only
kexec experiments. No internal/eMMC boot partition is written. A restart returns
to the internal kernel. GPU-backed labwc is not selected: the latest r5 probe
exited 139, while the current pixman session works. The proven r3 private GPU
libraries remain; r4/r5 experiments are omitted from the snapshot.

## Contents

- Working installed packages, NetworkManager profiles, SSH settings and ALSA state.
- Console unblank hook and the current vertical touchscreen transform.
- OpenRC `sl101-desktop` service depending on seatd and dbus; starts labwc with
  `WLR_RENDERER=pixman`, without experimental GPU library overrides.
- labwc autostart opens foot and NetSurf. Firefox remains unsuitable because
  its tested binary uses a NEON instruction unsupported by Tegra20.
- Runtime pseudo-filesystems, caches, logs and shell histories are excluded.

The snapshot is taken from the live filesystem, not an atomic offline backup.
The image filesystem and configuration are checked after assembly; cold boot,
automatic desktop startup, touch corners and visible browser use remain physical
qualification steps. Wi-Fi and SSH were tested live before capture, not from a
freshly flashed card. The new desktop service has not yet been cold-boot tested.
The demonstrated pixman session ran on the RAM-booted Grate kernel; its startup
on the internal 6.18.45 kernel is also pending. A desktop failure does not by
itself establish an SD/rootfs boot failure: check SSH and the service log first.

## Build and write

Build from the trusted private archive (the script only partitions an image file):

```sh
sudo sh scripts/sl101-nura-image-build.sh \
  tmp/sl101-nura/flashable/rootfs-private.tar.gz \
  tmp/sl101-nura/flashable/sl101-nura-adhoc-20260930.img \
  tmp/sl101-nura/flashable/package-refresh.tar.gz
```

The package-refresh overlay repairs sudo/PCRE files detected by `apk audit`
and incorporates qutebrowser-pyc plus package metadata changed near the end of
capture. It is part of this build's input, not evidence that qutebrowser works.
Only regenerated module indexes and an existing GStreamer helper link difference
may remain in the final package audit; unexpected missing library files must
be repaired before using the image.

Connect the intended SD to a host reader and unmount its partitions. Inspect the
whole removable device first, replacing `/dev/SD_DEVICE` with its actual path:

```sh
sudo python3 scripts/sl101-nura-flash.py \
  tmp/sl101-nura/flashable/sl101-nura-adhoc-20260930.img /dev/SD_DEVICE
```

Check the displayed model, serial and capacity against the intended card, then
repeat with `--write`. This overwrites that SD; the script rejects mounted,
non-removable, partition and undersized targets, checks the source checksum,
and verifies the written image by readback. Do not write the currently mounted
tablet root card through SSH. For this tablet the authorized card CID is
`035344534c31323880ac79a543010300`.

The root filesystem is initially about 4 GiB. After successful boot, optional
offline partition growth followed by `resize2fs` can use the remaining card
capacity. Keep the existing Debian spare card for recovery.

## First boot and recovery

On this already-provisioned tablet, insert the SD and cold boot. The copied
network profile may use `192.168.23.106`; verify the router lease if unavailable.
SSH host keys are intentionally preserved. Check:

```sh
uname -r
rc-service networkmanager status
rc-service sshd status
rc-service sl101-desktop status
cat /var/log/sl101-desktop.log
```

Expect 6.18.45 on cold boot. Check the display, four touch corners, keyboard,
NetSurf, ALSA and Bluetooth before calling the image qualified. If automatic
desktop startup fails, retain SSH and inspect the log; `rc-service
sl101-desktop stop` stops the experimental startup service. To disable it for
subsequent boots, use `rc-update del sl101-desktop default`.

If the tablet cannot reach SSH, power off and use the untouched Debian spare
card. No eMMC changes are part of this setup.
