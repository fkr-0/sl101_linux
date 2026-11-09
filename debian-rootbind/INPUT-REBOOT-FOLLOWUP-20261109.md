# SL101 Debian .100: Sway libinput omission and requested normal reboot

2026-11-09, ~15:36–15:46 CET. Target device:
`sltwrpbootdebian` = `192.168.23.100`, **not** the independent Nura
device `.106`.

## Proven input failure before reboot

The prior ad-hoc Debian Sway/Grate Prod70 launch used
`WLR_BACKENDS=drm`, `LIBSEAT_BACKEND=seatd`,
`WLR_RENDERER=gles2`, and
`WLR_RENDERER_ALLOW_SOFTWARE=0`. Native Nura deployment's
`scripts/sl101-user-session/sl101-desktop` does **not**
set `WLR_BACKENDS`, allowing wlroots to select the libinput
backend too. **DRM-only backend selection excludes libinput**.

On the live Debian Sway socket immediately before the reboot:

    swaymsg -t get_inputs
    []
    swaymsg -t get_seats
    [{"name":"seat0","capabilities":0,"devices":[]}]

The kernel independently recognized
`Atmel maXTouch Touchscreen` and `AT Raw Set 2 keyboard`.
The `keyd` service matched the keyboard at `0001:0002`,
created virtual keyboard/pointer, and ignored the touchscreen as
expected. Thus the **known compositor-layer defect** is an empty
Sway input seat, not proof of a broken kernel touchscreen driver
or failing keyd daemon. The previous successful screenshot/browser
tests were valid for GPU/network but **did not test input**.

Persistent Debian-side diagnostic saved on the tablet at
`/home/user/sl101-sway-input-before-reboot-20261109.log`
(6,047 bytes).

## Correct Nura-aligned fix for the next session (not yet tested)

Use the existing tracked Debian adapted Sway config at
`debian-rootbind/config/sway/config`, whose layout agrees
with the native Nura reference
`docs/sl101-device-config/home/user/.config/sway/config`:

    input "type:keyboard" {
        xkb_layout de
    }
    input "type:touch" {
        map_to_output LVDS-1
        calibration_matrix 1 0 -0.02 0 -1 1
    }

**Do not set `WLR_BACKENDS=drm`**. Unset `WLR_BACKENDS`
to enable wlroots automatic backend selection (or explicitly
select both `drm,libinput` after validating that combination).
Keep `LIBSEAT_BACKEND=seatd`,
`WLR_RENDERER=gles2`,
`WLR_RENDERER_ALLOW_SOFTWARE=0`,
`WLR_DRM_NO_ATOMIC=1` and the **private**
`/opt/sl101-debian-rootbind/bin/sl101-grate prod70 exec`
wrapper, without replacing system Mesa.

Before launching a browser, prove from the **new Sway socket**
that `swaymsg -t get_inputs` contains touchscreen and an
active keyboard (possibly `keyd virtual keyboard` rather than
the keyboard exclusively grabbed by keyd), and
`swaymsg -t get_seats` no longer says
`capabilities=0/devices=[]`. Inspect any libseat/libinput
errors. Only then launch Cog WPE with
`--platform=wl --webprocess-failure=exit` and a requested
real URL `https://www.tagesschau.de/`; confirm site loaded,
screenshot and user-verified touch/keyboard events. Keep an
independent SSH access channel and do not automatically overwrite
production Sway startup.

## Explicit operator-approved reboot and recovery status

Before reboot:

- Normal booted `7.0.1-postmarketos-grate`, root
  `/dev/mmcblk1p1`, eMMC CID
  `7001004d4d43333247447e682c336e00`;
- boot ID
  `ef4172eb-4c12-4c1c-94b3-325046a36e4d`,
  previous kernel boot at 11:13:48 CET;
- keyd + seatd active, video/render included in `id user`;
- exact LNX image and backups were **not** touched.

An earlier attempted reboot had been interrupted before execution.
At approximately 15:42 CET we saved
`/home/user/sl101-reboot-input-20261109.requested`,
stopped Cog and attempted Sway's clean IPC exit, executed
`systemctl reboot --no-wall` over privileged SSH. SSH
connection then closed (255) immediately after printing
`ISSUING NORMAL SYSTEM REBOOT NOW`, consistent with a reboot
initiated but **not alone proof of a successful new boot**.

At ~15:45:55 CET, host `192.168.23.123` could no longer
reach `.100` via ping or TCP/22;
`ip neigh show 192.168.23.100` returned `FAILED` and
SSH reported `No route to host`. Another device at
`192.168.23.106` remained pingable, so the local host was
not generally offline. **No new boot ID, kernel or root
readback could yet be obtained. Do not claim a successful
post-reboot boot or a fixed-input browser session.**

Before any subsequent remote launch, operator should inspect
the tablet screen and report whether it shows ASUS boot logo,
TWRP, Debian console, blank screen, or power-off. Depending
on this observation, distinguish boot-chain failure from an
otherwise successful Debian boot with no Wi-Fi association.
Do not blindly flash the 8-MiB LNX slot, assume Android has
booted, or modify the separate `.106` device.

Once `.100` is reliably reachable, verify
`cat /proc/sys/kernel/random/boot_id`,
`uname -r`, `findmnt -no SOURCE /`,
`id`, `systemctl is-active keyd seatd` and
`/opt/sl101-debian-rootbind/bin/sl101-grate prod70 check`,
then apply the input backend fix above. A fresh local/login
session should also carry persisted `video` and `render`
memberships.

This note is deliberately a diagnostic/next-step recipe, not
a claim of device-side fix deployment.
