# Strict SL101 Grate EGL/VDE video candidate — 2026-11-11

## Result boundary

Implemented host-side: scripts/sl101-gpu-video-gst.py with bounded unit tests.
Not yet proven: any video output, hardware pixel oracle, audio A/V sync,
GStreamer GL plugin availability, GL renderer mapping, DMABuf import,
continuous motion or E2E NuraBrowser on either physical tablet.

SSH from this controller currently fails for BOTH 192.168.23.100 and
192.168.23.106 with "Permission denied"; ssh-add reports no accessible
authentication agent. Port 22 being open is not authentication.
Do not reuse an unrelated ControlMaster, disable a sandbox or invent test results.

## Observed baseline (repository evidence)

- docs/sl101-gstreamer-vde-processing-path-audit-20261111.md: both tablets
  booted 7.0.1-postmarketos-grate-dmavde1 under an earlier qualified run;
  .100 GStreamer 1.26.2, .106 1.28.7. Both decoded 96 frames via real VDE,
  but output pads negotiated I420 system memory, NOT proven DMABuf/GLMemory.
- docs/sl101-106-dmavde1-hardware-qualification-20261111.md:
  VDE reference 96/96 exact padded/tight YUV; BO 216/216; GPU bilinear 120/120
  against its limited oracle. This does NOT prove GPU video presentation.
- nura-browser/docs/ci-staged-smoke-20261111.md: ARMHF WPEPlatform 2.54
  CI artifact staged inactive; no successful native headless hardware startup
  or Wayland window/pixels yet. Only the old Cog private root was runtime-tested.
- scripts/sl101-videoplayhw.sh uses CPU videoconvert/Wayland SHM.
  scripts/sl101-video-http-kms.sh uses kmssink scanout, NOT GLES rendering.
  Neither satisfies the user's STRICT GPU-rendering criterion.

## Candidate graph and checks

    file H.264 baseline/main MP4
      -> qtdemux -> h264parse -> v4l2slh264dec  [Tegra20 VDE hardware]
      -> video/x-raw(memory:DMABuf),format=DMA_DRM [default; fail if unsupported]
      -> glupload -> video/x-raw(memory:GLMemory)
      -> glcolorconvert [GLES shader YUV->RGBA]
      -> video/x-raw(memory:GLMemory),format=RGBA -> glimagesink
      -> Wayland EGL GLES2 -> Sway (Grate) -> KMS scanout

A/B --memory=system changes only decoder output cap to I420 system memory.
It permits CPU transfer/upload of raw YUV (not CPU colorspace conversion,
scaling, decoding or rasterization). It cannot be called zero-copy.

All operations are explicit, no autovideosink, videoscale, videoconvert,
waylandsink, kmssink, software decoder, Sway teardown or automatic fallback.
Runs only as an unprivileged Sway user on identified .106 (hostname plus
both MMC CIDs) with an exact pinned dmavde1 kernel. It reads the ACTUAL
running /usr/local/bin/sl101-sway process environ, requires Grate GLES2 with
WLR_RENDERER_ALLOW_SOFTWARE=0 and reuses its content-pinned Mesa/libdrm/
GBM paths plus GR3D serialization preload. Pixman Sway is rejected. Debian .100 is intentionally
blocked until its separate MMC identity and GStreamer EGL stack qualify.
Rejects a software GL environment, unexpected GPU vendor/path, no GLMemory
caps, errors and expired tests. The process-maps attestation requires a
literal grate_dri.so path; Mesa installations mapping only libgallium.so
will be conservatively marked unqualified until a stronger GL_RENDERER or
driver ioctl attestor is added. Do not bypass the gate based on name alone.
The logger stores process output and a JSON receipt if --evidence-dir set.

    python3 scripts/sl101-gpu-video-gst.py --dry-run --memory=dmabuf /path/video.mp4
    python3 scripts/sl101-gpu-video-gst.py --memory=dmabuf --seconds=30 \
      --evidence-dir=/tmp/gpu-video-proof /path/video.mp4

Run from the desktop's unprivileged Sway session, not as root and not via
unqualified SSH. On negotiation failure, compare explicit --memory=system.
Both test variants are experiments until pixel readback and frame timing pass.

## KMS transition policy

--mode=kms deliberately FAILS CLOSED. GStreamer's documented GL window
choices include Wayland, X11 and surfaceless; GBM display support exists in
GstGLDisplay, but that DOES NOT prove glimagesink can create a visible DRM/KMS
GBM EGL window and run a Grate shader. kmssink can efficiently scan out
VDE DMABuf without any GLES video rendering and therefore does NOT satisfy
strict GPU-raster policy. Do NOT label a fast KMS kmssink path GPU-rendered.
Do NOT use a guessed GST_GL_WINDOW=gbm. No silent UI compositor kill/switch.

For efficient operations, leave Sway running for routine GPU playback and
browser work; make direct KMS a separately gated one-owner session following
existing scripts/sl101-cog-kms-sway-session.py recovery supervision once a
real EGL/GBM GLES KMS client is qualified. A quick VT switch alone cannot
transfer DRM-master ownership or guarantee preserved GPU buffers. Record
switch latency, lost frames and rollback success rather than claim seamlessness.

## Needed E2E gates (no claim of completion)

1. Restore legitimate SSH authentication (not bypass), get exact kernel, CIDs,
   power, mounts, EGL/GLES Mesa and WebKit ELF hashes, Sway process, current
   DRM master and graphics lock. Cross-check .106 versus .100.
2. On .106 preflight local Gst GL factories, then strict renderer probe on
   deterministic 320x180/640x360 video. Capture actual negotiated caps,
   process maps, EGL renderer, WebProcess/graphics counters and output frames.
   If Grate driver maps are ambiguous, improve independent renderer attestation.
3. Verify direct YUV->GL path pixels with a known FFmpeg reference, monotonic
   timestamps, p50/p95 FPS, 60s audio A/V sync and no new dmesg faults.
   Benchmark DMABuf import vs system upload; no CPU RGB conversion.
4. Native browser staged CI headless then Grate Wayland EGL pixel/input test;
   explicit distinction WPE GPU Skia page raster from TextureMapper-only GPU
   composition. Disallow WEBKIT_SKIA_ENABLE_CPU_RENDERING=1 in a GPU-raster
   acceptance test. Modern full-web GPU raster remains unqualified.
5. Only after stable Sway results and dedicated EGL/GBM KMS renderer evidence,
   run supervised KMS vs Sway comparison, preserve rollback and restore Sway.

Run offline host acceptance: python3 -m unittest tests/test_sl101_gpu_video_gst.py,
make test and make check. No production promotion or device mutation here.
