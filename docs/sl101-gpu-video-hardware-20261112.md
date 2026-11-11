# SL101 GPU-only video / NuraBrowser hardware retry — 2026-11-12

## Verdict

GPU-only video playback: **BLOCKED; not accepted**.
Native NuraBrowser GPU Wayland E2E: **BLOCKED before startup**.
No KMS DRM-master handoff, reboot, flash, Mesa replacement, compositor
restart, sandbox bypass, software-video-render fallback or promotion occurred.

SSH access to .106 and .100 was restored using the existing unlocked
desktop gcr/ssh agent, /run/user/1000/gcr/ssh. The host environment's
SSH_AUTH_SOCK was unset. Host-key verification remained enabled.

## Hardware preflight

| | Nura .106 | Debian .100 |
|---|---|---|
| Kernel | 7.0.1-postmarketos-grate-dmavde1 | same |
| GStreamer | 1.28.7 | 1.26.2 |
| VDE v4l2slh264dec | yes | yes |
| glupload / glcolorconvert / glimagesink | yes | all absent |
| Sway | /usr/local/bin/sl101-sway PID 1436 | no process |
| battery | 70%; AC online=1, Discharging | 16%; AC online=0, Discharging |

.106 MMC: SD CID 035344534c31323880ac79a543010300;
eMMC CID 7001004d4d43333247448d402a656e00.
.100 was not exercised further because it lacked power and graphics prerequisites.

.106 active compositor: WLR_RENDERER=gles2,
WLR_RENDERER_ALLOW_SOFTWARE=0, MESA_LOADER_DRIVER_OVERRIDE=grate,
LD_PRELOAD=/usr/local/lib/gr3d_serialize.so.
Real prefix: /opt/grate-mesa25-musl-prod70-20261109/lib, NOT the prior
/usr/local/lib/sl101-grate-HASH/lib guess.
SHA256s: libgallium-25.0.7.so
be30623c7e753122dc95470a0829802fe9371dbdc93a6a9e081f3159e6d2fa89;
libEGL.so.1.0.0
ed10793c3186acdd3ff808f13ea6fabc1dcf9daf4d83ae925df5eda3cebb554c;
libGLESv2.so.2.0.0
9903d65b8cae3621262f225c981277da28d14a46f91a371f9699af62a1f31e61.

eglinfo -p wayland -a gles -B on live wayland-1 succeeded:
EGL 1.4, GL vendor Grate, renderer Tegra, GLES 2.0 Mesa 25.0.7.
This confirms real GPU context availability, not video output.

## VDE -> GLMemory failure, isolated to GstGL EGL

Input /home/user/health-360.mp4: H264 constrained-baseline,
640x360, progressive yuv420p, 17.25 seconds. Explicit intended pipeline:

    qtdemux -> h264parse -> v4l2slh264dec (VDE)
    -> memory:DMABuf/DMA_DRM -> glupload
    -> memory:GLMemory -> glcolorconvert
    -> memory:GLMemory/RGBA -> glimagesink

It never passed PAUSED/negotiated GLMemory: GstGLDisplayWayland reported
"failed to create dri2 screen" then SIGSEGV. An independent 64x64
synthetic diagnostic (videotestsrc, NOT a qualifying GPU-only video)
reproduced the same failure before touching VDE or media conversion.
GDB's gstglcontext thread recorded:

    SIGSEGV at 0x00004000
    #1 dri2_setup_screen
    #2 dri2_initialize_wayland
    #3 dri2_initialize

EGL_PLATFORM=wayland did not fix it. This matches the historic fault
address/stack in docs/sl101-grate-mesa-wayland-fix.md but does NOT
establish ABI mismatch or a generic NULL-screen bug. The historical
null-pointer patch 0001 is not an approved fix (see the upstream EGL
failure audit).

The corrected pinned player was streamed over authenticated SSH,
without installing it, and passed physical/Sway/provenance preflight.
Its actual hardware receipt at
.106:/tmp/sl101-gpu-video-20261112/receipt.json reports
exit_code=-11, timeout=false, GLMemory caps=false, success=false.
No software fallback was attempted.

Host logs (ignored evidence):
work/sl101-gpu-e2e-20261112/short-dmabuf-gst.log,
gst-egl-gdb-control.log, gst-egl-forced-platform-control.log,
new-player-hw-run2.log.

## mpv 0.41 GLES2 alternative

mpv --vo=gpu --gpu-context=wayland defaulted to GL desktop 2.0,
below its GL2.1 requirement. The explicit --opengl-es=yes flag
successfully selected Grate/Tegra GLES2. However:

- default GLSL shader fails on unsupported gl_FragCoord;
- --dither=no reveals a second error:
  "fragment TEX TEMP[2] exceeds temporary range";
- a separate, deliberately nonqualifying CPU YUV->RGBA diagnostic
  also fails with gl_FragCoord (tile_coord) even with
  --dither-depth=no and OSD disabled.

mpv's process exit=0 and advancing video clock are NOT proof of
rendered frames when Mesa logs "dropping draw, fragment shader
unavailable (compile failed)." No viable player is accepted yet.

VLC 3.0.23 was also tested with an explicit Wayland EGL OpenGL
output (--vout=gl --gl=egl_wl), no software fallback accepted.
It failed with "gl vout display error: parent window not available"
and "video output creation failed". VLC logged CPU swscale converters
and an exit=0 despite missing video. Thus VLC does not qualify either.
Host log: work/sl101-gpu-e2e-20261112/vlc-gl-wayland-try.log.
Evidence: mpv-gpu-wayland-test.log, mpv-gles2-wayland-test.log,
mpv-gles2-no-dither.log, mpv-gles2-rgba-control.log,
mpv-gles2-rgba-noditherdepth.log in the same host evidence directory.

Final read-only postflight: Sway PID 1436 and NuraLoumi panel PID 1792
still running, Wayland socket present, no lingering gst-launch/mpv/VLC.
The battery recovered to 72% Charging with AC online=1.
dmesg sample contained GDB ptrace attach but no new GPU reset signal.

## NuraBrowser GPU-only runtime gate

CI artifact exact source e0c2b0424c1244596bd0b2e9f40dd1ae54e968ac,
GitHub Actions run 43032042301, tar SHA
a15c922ac9e8e49a499e4b128c42cadbfb4ce96f5e44d2ecf2acc1dc8259920a
is staged inactive under /opt/nura-browser/releases on .106.
The device's CI-STAGED receipt says RUNTIME_QUALIFIED=false,
ACTIVATED=false; ELF SHA
67b5a5d6961ccb4ee100e40a6cb8300571e6a986978fd20e2fd20381a2e3a06b.

Four required GPU runtime paths in the private Cog root are missing:
- /etc/nura-browser/private-root-id
- /usr/libexec/nura-browser/nurabrowser-core
- /opt/nura-browser/grate/.sl101-overlay-sha256
- /opt/nura-browser/grate/usr/lib/arm-linux-gnueabihf/dri

The native --renderer=grate --platform=wayland launch therefore cannot
pass its security/runtime gates yet. Software Skia/softpipe headless
smoke would violate the GPU-only condition and was not run.

## Next discriminators

1. Compare EGL native-Wayland display and platform setup between
   eglinfo/mpv success and GstGLDisplayWayland failure. Audit matched
   libEGL, libgallium, Wayland protocol and DRI screen in GDB before
   modifying Mesa; never blindly apply historical null-check 0001.
2. After GstGL initializes, qualify exact VDE -> GLMemory caps,
   actual GLSL shader compilation, output pixel reference, FPS,
   audio timing, DMA layout, process maps and kernel stability.
3. For an alternate player use a small GPU YUV multipass shader
   compatible with Grate's proven register/sampler subset, instead
   of mpv's generic gl_FragCoord/TEMP-heavy GLSL. A NuraLoumi shell
   can provide playback controls but is not itself a renderer fix.
4. Install only CI-origin native NuraBrowser into a separately staged
   private glibc root with SHA-pinned glibc Grate overlay, then test
   GPU Skia page raster (not merely Grate compositing CPU page tiles).
5. Keep KMS switch disabled until an EGL/GLES KMS video renderer,
   exclusive DRM-master ownership, timing and rollback are proven.
   kmssink scanout by itself is not GPU rasterization.
6. Keep .100 read-only until stable power and GL dependencies exist.

No production or default state was promoted.
