# SL101 local video-file playback — VDE hardware decode qualified (2026-11-01)

## Verdict and ownership

SL101 video tooling belongs in **sl101_linux**, not android-infra (which retains
Android fleet metadata). The accepted Grate/Mesa driver (Gallium SHA-256
`68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade`)
proves a bounded GLES2 rendering candidate, **not** video decoding. The live
recovery compositor remains Pixman; this lane does not replace it.

Video *display* and video *decode* are distinct:

- **Software path** uses mpv with software decoding (`--hwdec=no`) and Wayland
  shared memory (`--vo=wlshm`). Any codec mpv supports works, but frame drops
  are heavy even at 360p (~50% on dual-core ARMv7 without NEON).
- **VDE hardware decode** uses the Tegra20 Video Decoder Engine via the
  GStreamer V4L2 stateless codec pipeline (`v4l2slh264dec` from `gst-plugins-bad`).
  The `tegra_vde` kernel module is loaded, `/dev/video0` is registered, and
  the decoder accepts `S264` (H.264 Parsed Slice Data) input with `YM12`/`YM21`
  output (Tegra non-contiguous tiled YUV420). **Only H.264 Baseline,
  Constrained Baseline and Main profiles** are supported by the hardware;
  High profile content requires transcoding first.
  **KMS direct display** (`--kms`, default): `v4l2slh264dec` → `kmssink` with
  `alsasink`. VDE DMABuf goes directly to the DRM plane — zero-copy, native
  24fps, correct pixels. Stops the Wayland compositor during playback and
  restarts it afterwards. **Wayland fallback** (`--wayland`): uses
  `waylandsink` with system-memory I420 frames and a 12fps videorate cap;
  produces distorted pixels due to buggy YM12→I420 conversion in the V4L2
  plugin — use only when KMS is not available.
  FFmpeg's `h264_v4l2m2m` wrapper does NOT work — it targets stateful V4L2
  decoders, not the stateless/request-API Tegra VDE.
- Historical `libvdpau-tegra` uses an X11/VDPAU output path; it is not a
  drop-in replacement for the Wayland/Pixman or WPE video pipeline.

ASUS SL101 Tegra20 is ARMv7-A, VFPv3-D16, **no NEON**. High-profile H.264,
high resolutions, and HEVC may overload its dual-core CPU. Start with a
low-complexity 360p MPEG-4 Part 2 + AAC MP4 compatibility file.

## Files and execution

- `scripts/sl101-video-play.sh`: mpv software-decode player with wlshm output,
  fail-closed file and Wayland socket checks, optional fullscreen/mute.
- `scripts/sl101-video-play-vde.sh`: GStreamer VDE hardware-decode player using
  `v4l2slh264dec` + `videorate` + `waylandsink`. H.264 Baseline/Main only.
  Default 12fps display cap (tunable with `--fps N`) to match the Pixman
  compositor's I420→RGBx software conversion throughput.
- `scripts/sl101-video-deploy.sh`: review-only-by-default, SHA-256 checked
  launcher deployment gated on pinned SSH identity, SD CID, kernel, root UUID,
  and existing SL101 qualification lock.
- `scripts/sl101-video-transcode.sh`: creates low-complexity MP4 copy using a
  **host** with FFmpeg; `--profile main` for VDE-compatible H.264. Refuses overwrite.
- `scripts/sl101-video-probe.py`: read-only JSON report of kernel identity,
  software/hardware prerequisites and VDE device status. Reports VDE as `ready`
  only when the full chain (module, device, driver, V4L2 formats, GStreamer
  decoder) is present.
- `tests/test_sl101_video.py`: device-independent tests (including filenames
  with spaces, safe argument handling, VDE qualification logic).

On a machine with FFmpeg installed, prepare a file:

    sh scripts/sl101-video-transcode.sh --height 360 --codec mpeg4 -- \
      "./original movie.mkv" "./sl101-ready.mp4"

For **VDE hardware decode**, transcode to Main profile H.264 (the VDE cannot
decode High profile content such as typical x264 BluRay rips):

    sh scripts/sl101-video-transcode.sh --height 360 --codec h264 --profile main -- \
      "./original movie.mkv" "./sl101-vde-main.mp4"

For Baseline/CAVLC (simpler, also VDE-compatible):

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

On the development host, review launcher deployment (no network or mutations)
then explicitly apply **only** when the authorized SL101 is available and the
qualification lane is free:

    sh scripts/sl101-video-deploy.sh
    # Explicit device change:
    # sh scripts/sl101-video-deploy.sh --apply

The hash-qualified launcher then lives at `/usr/local/bin/sl101-video-play`;
no video player package or video media is installed by deployment. For a local
source file, transfer it through your approved transport to a readable directory
on the tablet.

In the *normal running labwc Wayland session* (or its correct environment):

    python3 /path/to/sl101-video-probe.py  # copied separately as needed
    /usr/local/bin/sl101-video-play --dry-run -- "/path/movie.mp4"
    /usr/local/bin/sl101-video-play --fullscreen -- "/path/movie.mp4"

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

## Status, 2026-11-02

Device at `192.168.23.106` is live. Identity confirmed: SD CID
`035344534c31323880ac79a543010300`, kernel `7.0.1-postmarketos-grate`,
root UUID `6dd3675d-b5cf-41bd-9262-103c59321451`, labwc with
`WLR_RENDERER=pixman`, Wayland socket at `/run/sl101-desktop-user/wayland-0`.

**Installed packages** (device-side): mpv 0.41.0, v4l-utils 1.32.0,
ffmpeg 9.0.2, gstreamer 1.28.5, gst-plugins-bad 1.28.7 (includes
`v4l2codecs` with `v4l2slh264dec`), gst-plugins-good 1.28.7,
gst-libav 1.28.8.

**VDE hardware decode + KMS display qualified:**
- `tegra_vde` module loaded, `/dev/video0` registered as
  `tegra-vde` V4L2 stateless M2M decoder.
- Input: `S264` (H.264 Parsed Slice Data). Output: `YM12`/`YM21`
  (Tegra non-contiguous tiled YUV420 planar).
- Profiles: Baseline, Constrained Baseline, Main. Levels 1–5.1.
  **High profile is NOT supported** (the two on-device files are High profile).
- **KMS direct display (primary path):** `v4l2slh264dec` → `kmssink` with
  `alsasink`. VDE DMABuf goes directly to the DRM plane — zero-copy, no
  software colorspace conversion. Plays at native 24fps with correct pixels,
  crisp audio, and confirmed A/V sync over 3-minute test. The script stops the
  Wayland compositor for DRM master access and restarts it after playback.
  VT text is blanked during playback.
- **Wayland fallback:** `v4l2slh264dec` → `video/x-raw,format=I420` →
  `videorate` (12fps cap) → `videoconvert` → `waylandsink`. The Pixman
  compositor's I420→RGBx software conversion drops ~80% of frames at native
  24fps; the 12fps cap makes it sustainable but produces distorted pixels due
  to a buggy YM12→I420 system-memory conversion in the V4L2 plugin. Use only
  when KMS mode is not available.
- `WLR_RENDERER=gles2` does not work: Grate Mesa's EGL/DRI2 screen creation
  fails under wlroots, so `zwp_linux_dmabuf_v1` DMABuf import through the
  compositor is not available.
- GStreamer `v4l2slh264dec` → `fakesink`: 30-second 360p clip decoded in 2.1s
  (14× realtime).
- Full episode `test1-main.mp4` (854×480 Constrained Baseline, 24fps, AAC LC)
  played 3 minutes with VDE decode + KMS display + ALSA audio.

**ALSA configuration (WM8903):**
- DAC Companding: **off** (default was on; causes massive audio distortion).
- ADC Companding: **off**.
- Playback Deemphasis: **off**.
- State saved: `/var/lib/alsa/asound.state`.
- Boot restore: `/etc/local.d/sl101-alsa-restore.start`.

**mpv software decode qualified:**
- `mpv --hwdec=no --vo=wlshm` with PipeWire audio output connected and played
  the 360p test clip. Drops ~50% of frames at 24fps on the dual-core ARMv7
  (no NEON), A-V sync within ±35ms.

**Not yet qualified:** full 720p playback (requires High→Main transcode or
lower resolution), touch/keyboard stop, GL-accelerated compositor display path.

SSH from host requires explicit Wayland environment:
`XDG_RUNTIME_DIR=/run/sl101-desktop-user WAYLAND_DISPLAY=wayland-0`.

## Rollback

No installation performed unless the optional deploy `--apply` or a separate
package-manager command is explicitly run. To retire the launcher, first
verify its SHA-256 matches the reviewed deployment hash, then remove only
`/usr/local/bin/sl101-video-play`. Stop playback; remove the copied media or
optional native mpv package only if it was specifically
installed for this trial and no other application uses it. Revert just the
repository scripts to retire this lane. The tested Grate candidate and Pixman
default are unaffected.
