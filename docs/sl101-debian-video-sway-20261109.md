# SL101 Debian .100 — software video under native Grate/Sway, VDE/KMS qualification next

Test date: 2026-11-09 ~20:17–20:22 CET. Operator explicitly
requested video playback as the next milestone, either under Sway
or via direct KMS.

## Device and no-disruption controls

- SL101 `sltwrpbootdebian` = 192.168.23.100, boot ID
  `adcb71bc-c2ed-48a0-a560-cb408d2edc6d` (after the operator-approved
  normal reboot).
- Kernel `7.0.1-postmarketos-grate`; root `/dev/mmcblk1p1`,
  Debian 13 armhf/glibc, 1 GiB RAM.
- Existing Sway `/home/user/.config/sway/config`, real LVDS-1 output,
  Wayland socket `/run/user/1000/wayland-1`; Cog/WPE running
  on `https://www.w3.org/` simultaneously.
- `swaymsg -t get_inputs` now enumerates Atmel maXTouch, ASUS
  AT Raw Set 2 keyboard and keyd virtual keyboard/pointer. Thus the
  earlier omission of libinput is fixed **at the Sway backend level**.
  Physical response to actual user actions remains independently
  qualified by the input operator.
- Both mpv trials used **only** unprivileged process-local Wayland
  `wlshm`, no direct DRM or renderer switch and **no audio**.
  No changes to compositor, keyd, kernel, Mesa, system packages,
  audio routes or eMMC. Both players exited 0 with
  `Exiting... (End of file)`. Other Sway/Cog processes survived.

## Controlled clip comparison

The existing media qualification clip
`work/sl101-webkit-media-health-20261109/hw/health-360.mp4`
is a 17.25-second H.264 Constrained Baseline 640×360, 24 fps,
no-audio video. A lower-rate candidate was generated on the
**host**, not the tablet, from this same source:

    ffmpeg -hide_banner -nostdin -loglevel error -threads 2 \
      -i work/sl101-webkit-media-health-20261109/hw/health-360.mp4 \
      -map 0:v:0 -vf 'scale=320:180:flags=bilinear,fps=15' \
      -c:v libx264 -preset ultrafast -profile:v baseline -level 3.0 \
      -pix_fmt yuv420p -an -movflags +faststart \
      work/sl101-debian-video-sway-20261109/health-320x180-15fps-h264-noaudio.mp4

Low-rate test clip: 17.2667 seconds, 259 frames, 377,117 bytes,
SHA256 `739166dff0e83875713c18e59f80120f12371a78883565db928f28f75bce8247`.

Both clips were transferred to **/tmp only** on the Debian device.
The original device-side 640x360 clip has SHA256
`085183f793e7737168c9a5de875a908cefdb9e096fd72a20a612a4340351d7ec`.

Playback command for each test (replace `FILE` with the staged clip):

    XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 \
      mpv --no-config --no-input-default-bindings --no-input-cursor \
      --hwdec=no --vo=wlshm --ao=null --no-audio --framedrop=vo \
      --no-ytdl --no-load-unsafe-playlists \
      --input-ipc-server=/tmp/sl101-media-mpv-unique.sock FILE

Only one mpv test process was started at a time, with a
bounded 26–29 second subprocess deadline and a controlled shutdown.
A Python Unix-domain IPC client sampled `time-pos`,
`frame-drop-count`, `estimated-vf-fps`, `width` and `height`
about every 1.2–1.4 seconds (after IPC readiness).

| Metric | CPU H.264 640×360 @24 | CPU H.264 320×180 @15 |
| --- | ---: | ---: |
| Format, software Wayland VO | yuv420p, wlshm | yuv420p, wlshm |
| Playback time at final IPC sample | 13.5 s | 13.8 s |
| Frame-drop count at final IPC sample | **182** | **0** |
| Estimated input FPS | 24 | 15 |
| Exit status | 0 | 0 |
| Exit log | End of file | End of file |

For 640x360, the first sample at ~1.42 seconds had 18 drops;
drop counter grew monotonically (38,56,72,91,109,127,145,164)
to 182 at video time 13.5 seconds. The 320x180 case showed
zero counted drops in all twelve post-init samples spanning
video times 0.8 to 13.8 seconds, and then completed the clip
to EOF successfully.

**Conclusion:** Debian ARMHF software decode with wlshm is a
working fallback but 640x360@24 is not smoothly real time
(about half the theoretical frames lost by the last sample).
The 320x180@15 candidate is smooth by the
measured mpv frame-drop gate and completes end-to-end.
Note: mpv's `estimated-vf-fps` reports input framerate,
**not** measured real displayed FPS; 0 dropped frames and
normal playback-time advancement is strong, but does not
prove panel presentation timestamps without external
frame-capture oracle. This test deliberately excludes audio.

A screenshot was taken on .100 during the first 640x360
`wlshm` playback at
`/tmp/sl101-media-sway-mpv-videoonly-20261109.png`,
1280×800 PNG, SHA256
`51f1e3c62db62e4985fe84b9e236a5ce39f3de1b37fcff96885801e682c56bd2`;
Sway `get_tree` included `app_id=mpv` while Cog remained
present. No GR3D/DRM timeout/fault appeared in a read-only
kernel log filter after both experiments.

## Why KMS/VDE hardware video is still an independent gate

The kernel provides `/dev/video0`, `/dev/media0`
and a prior Alpine VDE decoder implementation exists, but
Debian currently only has `mpv 0.40.0` with
`wlshm`, `gpu`, `dmabuf-wayland` and
`drm` outputs. Direct GStreamer elements
`v4l2slh264dec`, `waylandsink`,
`kmssink`, `avdec_h264` are **not found** by
`gst-inspect-1.0` on Debian at this snapshot
(`gstreamer1.0-plugins-bad` package entry was found but
plugins may be absent, incompatible or misconfigured).
No claim of operational VDE hardware decoding is warranted.

Previously on Alpine under Sway, direct VDE → waylandsink
produced black frames and a tegra_vde mutex-owner kernel
warning; direct VDE → KMS was reported successful on
other runs. These **older Alpine observations do not
establish Debian parity**.

Next sequence for the video lane (separate from the input
and browser operator's Sway ownership):

1. Inventory Debian GStreamer plugin registry and native
   plugin package/library paths, including why packages
   are listed but elements not found; check any GLIBC/armhf
   missing shared object before changing packages.
2. Verify `/dev/video0` V4L2 driver name, supported codec
   formats/profiles and unprivileged access. Use only
   known Tegra20 H.264 Baseline/Main compatible clips.
3. Produce an explicit decoder-only GStreamer
   `fakesink` baseline (time progression, decoded buffers,
   no mutex WARN), before assigning the DRM master.
4. With operator control of the screen and an explicit
   compositor-stop/rollback gate, do a **bounded**
   VDE→`kmssink` test at 320x180 then 640x360.
   Restore previous Sway/Cog, VT and audio session
   reliably. Never concurrently acquire KMS DRM master
   while Sway owns it.
5. Only after safe direct KMS works compare
   `v4l2slh264dec` → video convert → Wayland
   against software fallback and validate rendered pixels.
6. WebKit's previously isolated AAC-triggered
   playback freeze (same compressed video bitstream
   works with audio removed) remains a **separate**
   timing/audio-sink problem; do not equate mpv success
   with Cog `<video>` success.

Source references:
`docs/sl101-video-playback.md`,
`docs/sl101-video-sway-0047-20261108.md`,
`docs/sl101-webkit-media-results-review-20261109.md`.
