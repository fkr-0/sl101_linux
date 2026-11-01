# SL101 local video-file playback — software-first v1 (2026-11-01)

## Verdict and ownership

SL101 video tooling belongs in **sl101_linux**, not android-infra (which retains
Android fleet metadata). The accepted Grate/Mesa driver (Gallium SHA-256
`68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade`)
proves a bounded GLES2 rendering candidate, **not** video decoding. The live
recovery compositor remains Pixman; this lane does not replace it.

Video *display* and video *decode* are distinct:

- v1 uses **mpv with software decoding** (`--hwdec=no`) and **Wayland
  shared memory** (`--vo=wlshm`). It does not depend on Grate.
- Tegra20 has a separate VDE video-decoder block. Linux may expose this through
  `CONFIG_VIDEO_TEGRA_VDE` and V4L2-request/stateless codec APIs. The
  **host-side** 7.0.1 Grate build tree
  `work/sl101-ec-v12-20261020/grate-build/.config` explicitly has
  `CONFIG_VIDEO_TEGRA_VDE=m`, and its
  `drivers/media/platform/nvidia/tegra-vde/tegra-vde.ko` was built.
  This is encouraging kernel-side evidence, **not** proof that the running
  SL101 loaded the same module, has a decoder node or supports playback.
  The installed kernel configuration, device node, userspace decoder, and
  correct decoded frames remain **unqualified**.
- Historical `libvdpau-tegra` uses an X11/VDPAU output path; it is not a
  drop-in replacement for the Wayland/Pixman or WPE video pipeline. Its old
  H.264 accelerator limitations must not be confused with general MP4 support.

ASUS SL101 Tegra20 is ARMv7-A, VFPv3-D16, **no NEON**. High-profile H.264,
high resolutions, and HEVC may overload its dual-core CPU. Start with a
low-complexity 360p MPEG-4 Part 2 + AAC MP4 compatibility file.

## Files and execution

- `scripts/sl101-video-play.sh`: actual local video-file player with mpv,
  fail-closed file and Wayland socket checks, optional fullscreen/mute.
- `scripts/sl101-video-transcode.sh`: creates low-complexity MP4 copy using a
  **host** with FFmpeg; refuses overwrite.
- `scripts/sl101-video-probe.py`: read-only JSON report of kernel identity,
  package/output prerequisites and VDE *possibility*. It never labels VDE
  working merely because a node or config is present.
- `tests/test_sl101_video.py`: device-independent tests (including filenames
  with spaces and safe mpv argument handling).

On a machine with FFmpeg installed, prepare a file:

    sh scripts/sl101-video-transcode.sh --height 360 --codec mpeg4 -- \
      "./original movie.mkv" "./sl101-ready.mp4"

Or for an **experimental H.264 Baseline/CAVLC** test, NOT a proven hardware
path:

    sh scripts/sl101-video-transcode.sh --height 360 --codec h264 -- \
      "./original movie.mkv" "./sl101-h264-baseline.mp4"

Inspect codecs before transfer:

    ffprobe -v error -show_entries stream=codec_name,profile,width,height,avg_frame_rate \
      -of json "./sl101-ready.mp4"

On the SL101, install *native* mpv only after checking the active musl/postmarketOS
package manager and repository; do not install glibc binaries into the musl
system. For an APK-based root the **operator-reviewed** commands are:

    apk search -x mpv
    apk info -e mpv
    # Optional, mutates device package state, only after package review:
    # apk add mpv

Do **not** run these against an unfamiliar filesystem or use `--force` APK
flags. An absent `mpv` package blocks v1 until an ARMv7 VFPv3-D16-safe native
player is built/installed; the existing glibc Cog browser root is **not**
implicitly used as a general application runtime.

After transferring a local file to a readable directory on SL101, use the
*normal running labwc Wayland session* (or its correct environment):

    python3 scripts/sl101-video-probe.py
    sh scripts/sl101-video-play.sh --dry-run -- "/path/movie.mp4"
    sh scripts/sl101-video-play.sh --fullscreen -- "/path/movie.mp4"

The script refuses to launch without a usable Wayland socket or mpv's `wlshm`
output. A remote SSH shell may not inherit the live session's
`XDG_RUNTIME_DIR` and `WAYLAND_DISPLAY`; do not invent defaults by chmod
on the compositor socket. The player does not change compositor, Mesa, audio
routing, screen mode, kernel, boot state or system packages. For audio-only
diagnostics, `--mute` disables audio; normal playback leaves mpv's audio
selection intact.

## Live qualification, required before "works on device"

1. Verify exact SD CID `035344534c31323880ac79a543010300`,
   kernel `7.0.1-postmarketos-grate`, current Pixman labwc session, and
   that the device has not entered another qualification lane.
2. Capture read-only `sl101-video-probe.py` JSON and package versions,
   including `mpv --version`, `mpv --no-config --vo=help`, and the codec
   stream report from `ffprobe`. Probing does **not** prove display playback.
3. Play a 360p 24fps MPEG-4 Part 2/AAC MP4 on the physical panel; verify
   moving picture, audio sync/volume, touch/keyboard stop, no SIGILL, no hang.
4. Record playback logs, CPU, RSS, dropped frames/A-V drift, and kernel
   `dmesg` before/after (no new GPU fault/reset). Repeat with 480p and
   H.264 Baseline as *separate* candidates. Preserve the original file.
5. Independently prove any VDE path with enumerated V4L2 codec formats,
   a suitable request-API decoder in userspace, confirmed hardware execution,
   correct output pixels and performance. Only then consider opt-in VDE
   acceleration; never relabel Grate/EGL as video decoding.
6. Preserve `WLR_RENDERER=pixman` recovery path. No unattended suspend,
   reboot, renderer promotion, firmware flash or default-player change.

## Status, 2026-11-01

Repository implementation and host-only automated tests can be completed without
device access; **no on-device playback is claimed** until steps 1–4 have actual
receipts. Last read-only SSH attempt to the pinned SL101 address
`192.168.23.106` failed with `No route to host`. Device package inventory,
codec throughput, display and audio are therefore unknown.

## Rollback

No installation performed by these scripts. Stop the playback process; remove
the copied media or optional native mpv package only if it was specifically
installed for this trial and no other application uses it. Revert just the
repository scripts to retire this lane. The tested Grate candidate and Pixman
default are unaffected.
