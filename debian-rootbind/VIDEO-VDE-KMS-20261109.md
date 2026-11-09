# Debian SL101 .100: Sway software video vs native Tegra-VDE / DRM-KMS

**Qualification date:** 2026-11-09, evening CET.

**Device identity:** `sltwrpbootdebian` at `192.168.23.100`,
ASUS SL101 Tegra20 ARMv7 without NEON, Debian 13 armhf/glibc on
`/dev/mmcblk1p1`, running
`7.0.1-postmarketos-grate`. eMMC CID
`7001004d4d43333247447e682c336e00`.
No bootloader, LNX, Android, kernel, firmware or U-Boot changes
were performed in this lane. The unrelated `.106` device was not used.

## Summary and release decision

| Path | Direct evidence | Current verdict |
| --- | --- | --- |
| Sway / mpv / software H.264 / `wlshm`, 640×360×24 | Playback reaches EOF; 182 frame drops, video time advances 1.42→13.5 s | **Not smooth** |
| Sway / mpv / software H.264 / `wlshm`, 320×180×15 | Playback reaches EOF; 0 frame drops in sampled statistics | **Usable low-resolution fallback**, visual fidelity still operator-dependent |
| VDE `v4l2slh264dec` → `fakesink` | 30 frames, 0.218820497 s, EOS/exit 0, no new kernel warning during this short run | **Decoder functional** |
| VDE `v4l2slh264dec` → KMS `kmssink` | Direct 17.250494498-second playback, `DMA_DRM`/`YU12` DMABuf, EOS/exit 0, 1280×800 display | **Technically functional but unsafe kernel mutex ownership warning; do not promote** |

The first two mpv results come from the concurrently coordinated
`gpt6-sl101-100-input-media-20261109-evening` run, recorded in
`docs/sl101-debian-video-sway-20261109.md` (commit `83d4d82`).
The gray mpv video region captured in the screenshot is consistent
with an intentionally gray frame of the test clip (reference frame
at 2 s: mean RGB ≈119/117/122, similar to the sampled screenshot
interior). Thus **do not call the screenshot evidence of Grate
corruption**. A single screenshot cannot establish motion smoothness.

## Native Debian installation (SD root only)

Apt installed Debian 13 armhf packages, without replacing Mesa or
rebooting:

- `gstreamer1.0-tools 1.26.2-2`
- `gstreamer1.0-plugins-base 1.26.2-1+deb13u2`
- `gstreamer1.0-plugins-good 1.26.2-1+deb13u2`
- `gstreamer1.0-plugins-bad 1.26.2-3+deb13u3`

These and their dependencies were installed on `.100` through
`apt-get --no-install-recommends`. Final `dpkg-query` result is
`ii` for all four. `gst-launch-1.0`, `qtdemux`,
`h264parse`, `v4l2slh264dec`, `fakesink`, `kmssink`,
`waylandsink` and `videoconvert` are present. The
`alsasink` element is **not** installed, and no audio sink
was part of this hardware playback test.

Kernel: `tegra_vde` loaded, `/dev/video0` has driver name
`tegra-vde`. Its capture formats were not substituted with
a generic `NV12` assumption.

Reference file on Debian SD:

    /home/user/sl101-video-ctl-360-audio-20261109.mp4

SHA256:
`a551581664b854bc507fb2b0272772fcef03cfada1a71bac7ddcf23d041b5808`.

Media: H.264 **Constrained Baseline**, 640×360,
24/1 fps, 17.250 seconds. The audio stream in this input
was deliberately excluded from these video-only experiments.

## Decoder-only qualification

Actual pipeline, bounded and without DRM master:

    gst-launch-1.0 -e -v -m \
      filesrc location=/home/user/sl101-video-ctl-360-audio-20261109.mp4 ! \
      qtdemux name=demux demux.video_0 ! queue max-size-buffers=4 ! \
      h264parse ! v4l2slh264dec ! \
      identity eos-after=30 ! fakesink sync=false

Results: valid H.264 caps, hardware decoder output
`video/x-raw,format=I420` 640×360 @ 24 fps,
30 frames and valid EOS in **0.218820497 s**.
Exit 0. No new mutex warning was observed for this short
decoder-only experiment. The first syntax-only attempt used an
incorrect qtdemux element name, failed before playback and was
corrected; do not mistake that parse error for a VDE failure.

## Direct DRM/KMS video-only test

The existing Debian Grate Prod70 Sway session
(`WLR_BACKENDS=drm,libinput`) was gracefully stopped using its own
Sway IPC to release DRM master. An independent root-owned
`/tmp/sl101-debian-vde-kms-supervisor-20261109.sh`
launched the short test and used an EXIT trap to restore
Sway whether the GStreamer pipeline succeeded or failed.

Actual GStreamer pipeline:

    gst-launch-1.0 -e -v \
      filesrc location=/home/user/sl101-video-ctl-360-audio-20261109.mp4 ! \
      qtdemux name=demux demux.video_0 ! \
      queue max-size-buffers=3 ! h264parse ! v4l2slh264dec ! \
      kmssink sync=true

The KMS sink queried the real `tegra` DRM driver:
`connector-id=66`, `crtc-id=64`, `plane-id=42`,
display **1280×800**, DRM PRIME import/export supported.
Decoder and KMSSink agreed on:

    video/x-raw(memory:DMABuf)
    format=DMA_DRM
    drm-format=YU12
    width=640 height=360 framerate=24/1

The pipeline **PREROLLED**, entered **PLAYING**, ran for
**17.250494498 s**, emitted **EOS**, and exited **0**.

This proves a real VDE-to-KMS DMA-Buf path without an obligatory
`videoconvert` or CPU YUV/RGB copy. It **does not prove**
correct on-screen video pixels, absence of individual display frame
drops or synchronized sound. There was no independent photographic
human visual acceptance, and no audio branch was used.

## Kernel defect: mutex ownership violation (P1 safety gate)

A new kernel warning **was** emitted during the full VDE/KMS run,
even though GStreamer returned success:

    [ 4230.308156] WARNING: kernel/locking/mutex.c:949
       at __mutex_unlock_slowpath+0xf8/0x344,
       CPU#1: kworker/1:4/59
    [ 4230.308203] DEBUG_LOCKS_WARN_ON(__owner_task(owner) != get_current())
    [ 4230.308449] Workqueue: tegra-vde tegra_decode_complete [tegra_vde]
    [ 4230.308657] __mutex_unlock_slowpath
       from tegra_vde_h264_decode_wait+0xd4/0x10c [tegra_vde]
    [ 4230.308709] tegra_vde_h264_decode_wait
       from tegra_decode_complete+0x44/0x68 [tegra_vde]

The kernel reports itself tainted `G W` after this warning.
This reproduces the ownership bug already analyzed in
`docs/sl101-vde-video-path-20261108.md`: an ordinary
mutex cannot be released by a different worker task than its owner.
The apparent decode/display success **does not excuse**
an invalid kernel synchronization contract.

**Do not ship direct VDE/KMS as stable or conduct repeated VDE
stress/media service tests before the `tegra_vde` mutex
ownership/async completion lifecycle is repaired and qualified.**
Do not confuse this VDE issue with Mesa/Grate GLES2 resource
management or the separate `DONT_KMAP` kernel experiment.
A future kernel change must be built/reviewed/boot-qualified
independently with APX recovery still available.

## Verified desktop rollback and process state

Supervisor logs show:

    SWAY_RELEASED_DRM 2026-11-09T20:33:07+01:00
    KMS_PIPELINE_EXIT=0 2026-11-09T20:33:32+01:00
    SWAY_RESTORED 2026-11-09T20:33:33+01:00

Sway returned using private `Grate Prod70` with
`WLR_BACKENDS=drm,libinput`, GLES2 renderer, seatd,
German keyboard layout. `swaymsg -t get_inputs` still
included the Atmel touchscreen, AT Raw Set 2 keyboard,
keyd virtual keyboard and virtual pointer; `LVDS-1`
remained active. The prior Cog process had lost its Wayland
display and was safely terminated; a new Cog/WPE instance
was started with `https://www.w3.org/` and a visible
`com.igalia.Cog` window.

No kernel reboot, no KMS/Wayland permanent service or
startup change, no bootloader/partition write and no
system Mesa replacement occurred.

## Evidence and follow-ups

Private host logs copied read-only from device:

- `work/sl101-debian-vde-kms-20261109/sl101-debian-vde-decoder-30frames-corrected-20261109.log`
- `work/sl101-debian-vde-kms-20261109/sl101-debian-vde-kms-direct-20261109.log`
- `work/sl101-debian-vde-kms-20261109/sl101-debian-vde-kms-supervisor-20261109.log`
- `work/sl101-debian-vde-kms-20261109/kernel-vde-mutex-warning.log`
- `work/sl101-debian-vde-kms-20261109/sl101-debian-vde-kms-sway-restore-20261109.log`
- `work/sl101-debian-vde-kms-20261109/sl101-debian-vde-kms-cog-restored-20261109.log`

Next qualification gates: (1) repair VDE async mutex
ownership, (2) repeat **bounded** KMS test and obtain actual
visual pixel verification, (3) add and qualify the ALSA/AAC
audio branch and A/V sync, (4) only after these consider a
supervised production KMS player/HTTP streaming mode. Until
then, the low-resolution mpv `wlshm` path is the safer
desktop-preserving alternative.
