# SL101 .106 Grate/GstGL EGL diagnostic — 2026-11-12

OCP identity: SL101-LINUX-OCP-SL101-GRATE-GST-GL-VIDEO-20261112-20261112-058763.
Base: 1b38817d8ee3b5e79a25e2c74786ce8c19359452.

## Verdict

**BLOCKED: no visible H.264 video or accepted GPU pixels.**
The implementation in scripts/sl101-gstgl-egl-probe.py and
scripts/sl101-grate-egl-probe.c is a reproducible, fail-closed
diagnostic, not a released video player. Do not promote it.

Only the physical Alpine/musl .106 (sl101-nura,
7.0.1-postmarketos-grate-dmavde1) was used. The Python harness
attests host/kernel/SD/eMMC CIDs, unprivileged UID, existing Sway
executable/owner, renderer environment, private musl Grate ELF hashes,
Wayland socket, and holds the existing GPU operation lock nonblocking.
The direct driver environment is cloned from the running compositor.
The staged tools and full raw evidence are only in /tmp on .106,
and ignored work/sl101-gstgl-egl-058763/ on the host. No system
Mesa or GStreamer installation, compositor restart, KMS DRM-master
takeover, kernel/boot change, reboot, GPU reset, software-video sink,
or .100 access occurred. Sway PID 1436 remained alive.

## Observed independent experiments

| Test | Result |
|---|---|
| eglinfo, Wayland GLES | exit 0, Grate / Tegra 25.0.7, private EGL and Gallium 25 mapped |
| GStreamer synthetic 64x64 videotestsrc to glupload, glcolorconvert, GLMemory RGBA, glimagesink | EGL says failed to create dri2 screen, no GLMemory caps, timeout at 12 s, terminated -15 |
| libgstgl-1.0.so.0 ELF DT_NEEDED | links libGL.so.1 AND libEGL.so.1 |
| libGL.so.1 ELF DT_NEEDED | links libgallium-26.2.4.so |
| GStreamer runtime /proc maps | BOTH private libgallium-25.0.7.so and system libgallium-26.2.4.so |
| native eglGetDisplay with real wl_display | EGL 1.4, private Grate GLES2 context created |
| native eglGetPlatformDisplayEXT WAYLAND | same EGL 1.4 and private GLES2 context |
| native platform after dlopen(libGL.so.1, RTLD_GLOBAL) | loads BOTH Galliums; EGL initialization still succeeds |
| Native FBO RGBA8 1x1 and 64x64, texture attachment | GL_FRAMEBUFFER_UNSUPPORTED, status 0x8CDD, with GL_VENDOR=Grate, GL_RENDERER=Tegra |

The side-by-side libGL loader A/B is important: loading both Galliums
is a concrete risk, but is **not alone sufficient to reproduce** the
GstGL initialization failure. The old struct ABI mismatch explanation
remains a hypothesis. The earlier GDB SIGSEGV at 0x00004000
inside dri2_setup_screen was not reproduced as a fresh SIGSEGV here:
the bounded GStreamer fixture stalled after an EGL warning.
Neither successful EGL initialization nor an unavailable FBO is a
passing GPU pixel oracle.

Also, the GstGL child did not map the private libGLESv2.so by the
sampling deadline; that EGL/Gallium pair alone does not prove a GLES
context. Native C cases mapped all three private ELFs. In both
Gallium libraries the exported driCreateNewScreen3 symbol exists
with their distinct symbol versions; an incorrect actual binding
has NOT been shown.

## Evidence

- Machine-readable compact digest: docs/evidence/sl101-grate-gstgl-egl-20261112/receipt-summary.json.
- Full target run3: /tmp/sl101-gstgl-egl-058763/evidence3/.
- Native 64x64 run5: /tmp/sl101-gstgl-egl-058763/evidence5/.
- Ignored host copies: work/sl101-gstgl-egl-058763/evidence3/
  and work/sl101-gstgl-egl-058763/evidence5/.
- Earlier baseline and GDB stack: docs/sl101-gpu-video-hardware-20261112.md.
- Invalid historical Mesa NULL-guard audit:
  docs/upstream/grate-followups-20261103/06-egl-null-failure.md.

Host dry run: python3 scripts/sl101-gstgl-egl-probe.py

Host tests: python3 -m unittest discover -s tests -p test_sl101_gstgl_egl_probe.py

Target-only C compile (no installation):

    cc -std=c11 -Wall -Wextra -Werror -O0 \
      sl101-grate-egl-probe.c -o eglprobe \
      $(pkg-config --cflags --libs egl glesv2 wayland-client) -ldl

Target execution as the Sway user, using a **new** private evidence directory:

    python3 sl101-gstgl-egl-probe.py --run-fixture \
      --c-binary /tmp/sl101-gstgl-egl-058763/eglprobe \
      --out /tmp/sl101-gstgl-egl-058763/evidence3

The flag --native-only skips the GstGL fixture and compares only
native C EGL cases. All hardware modes require the existing GPU lock.
No command in this document authorizes running the device binary on .100.

## Source-level candidate fix and falsification gates

The distro GStreamer GL library is linked with desktop libGL.so.1.
Setting GST_GL_API=gles2, GST_GL_PLATFORM=egl and
GST_GL_WINDOW=wayland does not unlink desktop libGL and Gallium 26.
This follows from target readelf and /proc maps, not just config guesses.

Prepare a **private staged musl gst-plugins-base GL build** with the
precise distro-compatible GStreamer source and candidate Meson options:

    -Dgl_api=gles2 -Dgl_platform=egl -Dgl_winsys=wayland

These option names are present in:
https://sources.debian.org/src/gst-plugins-base1.0/1.28.9-1/meson.options
They are not a verified working build for the installed 1.28.3
GStreamer GL plugin / 1.28.7 core. Before touching the device,
pin source and compatible ABI, verify musl/ARM ISA and build artifacts,
audit readelf DT_NEEDED (no desktop libGL), runtime process maps
(no second Gallium), and stage only via isolated process-local paths.
Keep the live /usr/lib and Sway's Mesa completely unchanged.

If that build still fails, obtain a precise GDB source-level breakpoint
at dri2_setup_screen and gst_gl_display_egl_get_from_native: check
the actual resolved DRI factory, dri_screen and pipe_screen pointer
addresses, EGLConfig, dlopen order, Wayland wl_drm and linux-dmabuf
globals. The GStreamer implementation tries
eglGetPlatformDisplay/eglGetPlatformDisplayEXT for supported Wayland,
then falls back to eglGetDisplay; our native A/B did not distinguish
these entry points as a root cause. Never apply historical Mesa
patch 0001 (bare NULL guard with invalid error propagation).

The native renderer is independently blocked by Grate's unsupported
RGBA8 FBO; qualify a real GLES2 shader framebuffer target, strides
and texture formats before integrating actual VDE I420/NV12 samples.
Acceptance still requires: compile/link and GL errors of short
low-TEMP GLES2 shader; color/black/nonzero moving frame pixel oracle;
DMA plane/offset/pitch proof; no CPU YUV-to-RGB conversion; 24-fps
frame/PTS progression; WayVNC screenshot; A/V sync; no drop/fallback.
This diagnostic proves none of those acceptance gates.

## NuraLoumi boundary

The playerd audio feature f7ac777 and integration bd88766 must
continue reporting UNSUPPORTED_GPU. No NuraLoumi panel/shell files
were edited. Only after GPU video qualification should a separate
backend expose open/play/pause/stop/seek/volume, timing, error and
GPU_QUALIFIED state; do not bind this diagnostic as a player backend.
