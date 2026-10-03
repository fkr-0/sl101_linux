# SL101 browser GPU capability qualification — 2026-10-03

Task: `SL101-BROWSER-CAPABILITY-20261003`  
Dispatch attempt: `ed8fb0956cdf4701a9a2c42f74f3263b`  
Implementation packet: `c0504f61-b048-4705-ab8d-e2fb04e62a13`  
Scope: evidence/research only; no live graphics, browser-profile, kernel, boot,
mount, GPU-device or desktop mutation.

## Executive result

The **best current GPU-browser candidate is WPE WebKit 2.54.x**, with Cog 0.18.x
usable only as a bounded legacy-API qualification harness. Upstream still states
that WPE's minimum embedded graphics floor is EGL + OpenGL ES 2, which matches
the API level demonstrated by the accepted Grate Mesa 25.0.7 candidate. Modern
WPE 2.54 is not the old TextureMapper stack, however: WPEPlatform is now the
forward API and Skia is the web-process compositor, with GBM/libdrm, DMA-BUF
sharing and sandboxed GPU/media access all requiring new qualification.

**Firefox hardware WebRender is not a sensible next GPU trial with the current
accepted Grate capability.** Current Firefox Linux source hard-blocks WebRender
when GL major version is below 3. The accepted Grate evidence is OpenGL ES 2.0,
so the requirement is not met. The current Firefox 140.16 installation should
remain an untouched software-rendered recovery/reference browser.

**QtWebEngine/qutebrowser is blocked at the CPU baseline before graphics are
considered.** Current Chromium ARM configuration hard-codes NEON, following the
December 2025 removal of the non-NEON ARM build toggle. Tegra20 has no NEON.
Using an old Chromium/QtWebKit line to regain no-NEON support would violate the
security constraint and is not proposed.

**WebKitGTK 2.54.x is technically worth keeping as a second WebKit option, but
not as the first hardware trial.** It shares modern Skia/ANGLE/GBM requirements
with WPE and adds GTK overhead; Nyxt additionally adds SBCL/application
overhead. Current WebKitGTK 2.54.1 is the maintained baseline to consider, not
an older engine.

The main unresolved risk for WPE/WebKit is now **CPU/build qualification**, not
the historical GLES2 headline: a full current WebKit/Skia/JSC/GStreamer build
must be proven free of NEON and unsupported d16-d31 instructions on the actual
linked binaries and then exercised on Tegra20.

## Current SL101 state — live observation

Read-only live observation is archived in:

- `work/sl101-browser-capability-20261003/live-state.json`
- collector: `work/sl101-browser-capability-20261003/collect-live-state.py`

At 2026-10-03 16:02 UTC:

| Item | Observed state | Interpretation |
|---|---|---|
| Kernel | `7.0.1-postmarketos-grate` | expected Grate kernel is live |
| SD CID | `035344534c31323880ac79a543010300` | expected device |
| accepted private Gallium | both known `68a78e18…` prefixes still hash exactly to `68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade` | preserved candidate exists |
| live labwc renderer | `WLR_RENDERER=pixman` | current desktop is **not** GPU-rendered |
| live labwc mapped Gallium | `/usr/lib/libgallium-26.2.3.so`, SHA-256 `45205e54…` | mapped system library is not the accepted `68a…` private candidate; mapping alone is not proof of GPU use |
| Firefox package | `140.16.0esr-1~deb13u1` | recovery/reference version remains installed |
| Firefox graphics mode | software WebRender forced; layers acceleration disabled; WebGL disabled | no GPU-browser claim |
| Firefox process GL maps | none in observed Firefox processes | consistent with software mode |
| Firefox child sandbox | content/socket/RDD/utility processes observed with `NoNewPrivs=1`, `Seccomp=2`; distinct user namespaces present for several subprocesses | sandbox remains active; future GPU qualification must preserve it |

No EGL/GLES context was created during this task and no live GPU probe was
started.

### Preserved accepted Grate evidence

The preserved accepted candidate remains:

`68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade`

Relevant prior evidence:

- `docs/sl101-working-egl-20261003.md`
- `work/sl101-compositor-semantics-20261003/evidence-r2/grate/labwc.log`
- `work/sl101-compositor-review-20261003/evidence/live-68a-precision-summary.json`

That evidence demonstrated:

- EGL 1.4
- Wayland/GBM platform support
- `EGL_EXT_image_dma_buf_import`
- `EGL_EXT_image_dma_buf_import_modifiers`
- `EGL_MESA_image_dma_buf_export`
- `EGL_WL_bind_wayland_display`
- `GL_OES_EGL_image`
- OpenGL ES 2.0, Mesa 25.0.7
- Grate / Tegra renderer
- a high-precision visible compositor comparison with no structural mismatches
  and no recorded GPU-fault delta in the accepted trial

This proves a useful EGL/GLES2 + buffer-sharing **candidate**, not ES3/GL3,
browser WebGL, browser GPU rasterization, hardware video decode, or current live
desktop acceleration.

## Capability layers

These are deliberately separate gates:

1. **EGL context creation** — can the process create the intended hardware
   context and identify Grate/Tegra rather than software GL?
2. **GL/GLES feature level** — which API version/extensions are actually
   implemented, not merely advertised?
3. **GPU composition/rasterization** — does the browser's compositor/raster
   path execute on hardware and survive real page workloads?
4. **WebGL** — browser-facing ANGLE/WebGL capability has additional API,
   translation and security constraints.
5. **JavaScript/JIT** — generated CPU code must respect ARMv7-A/VFPv3-D16 and
   no-NEON just as static ELF code must.
6. **Video decode** — VA-API/V4L2/GStreamer/codec and sandbox-device access are
   independent of 3D rendering.
7. **Buffer sharing** — Wayland/GBM/DMA-BUF import/export and synchronization
   must work between browser/GPU/compositor processes.
8. **Sandbox** — GPU/media access must work with the engine's normal sandbox;
   disabling the sandbox is a failed qualification, not a workaround.

## Engine capability matrix

Legend: **YES** = current evidence/source supports proceeding; **NO** = current
known requirement is not met; **UNKNOWN** = requires bounded qualification.

| Engine / shell | CPU / JS | EGL + GL/GLES | GPU composition / raster | WebGL | sandbox / buffer sharing | video decode | Current Grate verdict |
|---|---|---|---|---|---|---|---|
| Firefox current / WebRender | newer tested Firefox already SIGILLs on this CPU; ESR140 normal JS was proven | **NO for WebRender:** current Linux source blocks GL major <3; accepted Grate is GLES2 | **NO with accepted 68a capability** | current recovery profile disables it; GLES2-only browser path unqualified | current ESR140 child sandbox is live-proven; future GPU-process path unqualified | separate VA-API/V4L2 probe path; unqualified | **insufficient for hardware WebRender** |
| Firefox ESR140.16 recovery | **YES**, HTTPS + JS already proven | software path only by policy | software WebRender | disabled by recovery profile | **YES** for existing content-process sandbox | unqualified | **keep as recovery, do not relabel GPU** |
| WPE WebKit 2.54.x / Cog 0.18.x harness | Debian armhf ABI baseline fits VFPv3-D16, but complete WebKit/Skia/JSC non-NEON output remains **UNKNOWN** | upstream minimum is EGL + GLES2, so API floor is **YES**; exact private glibc Grate build still needed | **UNKNOWN but plausible**; 2.54 uses Skia, not historical TextureMapper | **UNKNOWN**; current build uses ANGLE for WebGL; WebGL2 is not supported by the existing GLES2 evidence alone | **UNKNOWN**; WPE GPU process depends on GBM/libdrm; accepted EGL extensions are encouraging; Bubblewrap must stay enabled | **UNKNOWN**; GStreamer/V4L2 and sandbox device policy are separate | **best candidate; proceed through serial gates** |
| WPEPlatform 2.54.x native harness | same as WPE row | same; WPEPlatform Wayland/DRM/headless is current forward API | **UNKNOWN but preferred long-term path** | same ANGLE question | same GBM/libdrm/DMA-BUF + Bubblewrap gates | same GStreamer/V4L2 gate | **preferred after/alongside compatibility harness** |
| WebKitGTK 2.54.1 / Nyxt | WebKit/JSC non-NEON remains **UNKNOWN**; Nyxt/SBCL resource fit also unqualified | no immediate GLES2 disqualifier established; same modern Skia/GBM stack | **UNKNOWN** | **UNKNOWN**, ANGLE-backed | **UNKNOWN**; GTK Wayland + GBM/libdrm; normal WebKit sandbox required | **UNKNOWN**, GStreamer separate | **possible second choice, not first trial** |
| QtWebEngine / qutebrowser | **NO:** current Chromium ARM build hard-codes NEON | moot until CPU gate solved | moot | moot | Qt requires userns + seccomp-bpf; must not use `--no-sandbox` | moot / separate Chromium media path | **blocked for current maintained engine** |

## Engine-specific findings

### Firefox

Current Firefox Linux source contains an explicit WebRender qualification gate:
GL major versions below 3 are blocked with
`FEATURE_FAILURE_OPENGL_LESS_THAN_3`. The preserved Grate browser-relevant
evidence is GLES 2.0, therefore a Firefox GPU trial against this exact accepted
capability would begin from a known upstream block.

A future Firefox GPU trial only becomes rational if a newer Grate/Mesa candidate
can honestly expose and pass the GL3/ES3-equivalent requirements Firefox uses,
without forcing blocklist overrides. Even then, the CPU binary itself must first
pass the Tegra20 instruction gate.

Security note: Mozilla's 2026-09-29 enterprise release notes state that ESR 153
is current and ESR 140 went out of support with Firefox 157; 140.17.0 is the
final ESR140 build. The installed 140.16 remains valuable as a known-working
recovery/reference path but is not a current maintained browser baseline for
routine untrusted browsing.

### WPE WebKit / Cog

WPE remains the strongest match because current upstream documentation still
states a minimum of EGL + OpenGL ES 2 + basic GStreamer. That is materially
different from Firefox's GL3 WebRender gate.

But "GLES2 is enough" is only the **entry floor**. WPE 2.54 changed the relevant
implementation:

- WPEPlatform is stable/default; new applications should target it.
- Cog stops at the 0.18.x stable line and uses the legacy libwpe API.
- Web-process compositing moved to Skia.
- Cairo 2D rendering was removed.
- `USE_SKIA` defaults on.
- Linux Bubblewrap sandbox defaults on.
- GPU process requires GBM, and GBM requires libdrm.
- WebGL enables ANGLE.
- DMA-BUF paths and sandbox access to V4L2 devices have active, recent fixes.

Therefore the first success criterion is not merely "Cog window appeared." It
must prove a current 2.54 engine, a non-NEON/D16-safe binary set, a Grate/Tegra
EGL context, correct buffer sharing, sandbox preservation, and objective GPU
activity while rendering real content.

Cog 0.18.x is acceptable as a short-lived **legacy-API** qualification shell:
WPE's current compatibility table explicitly pairs WPE WebKit 2.48.x-2.54.x
with libwpe 1.16.x, WPEBackend-fdo 1.16.x and Cog 0.18.x. The durable browser
integration should move toward WPEPlatform rather than extend the deprecated
API.

### WebKitGTK / Nyxt

WebKitGTK 2.54.1 is current as of 2026-10-02. Its current build configuration
likewise defaults to Skia, supports Wayland, uses GBM/libdrm for the GPU process,
and uses ANGLE when WebGL is enabled.

Nyxt explicitly recommends using the latest WebKitGTK for security and uses
WebKitGTK as its normal renderer, but it adds SBCL and its own application
footprint. On SL101, WPE gives a smaller surface for answering the fundamental
question "can current WebKit/Skia render through Grate safely?" before adding a
heavier shell.

### QtWebEngine / qutebrowser

Current Chromium `build/config/arm.gni` hard-codes:

- `arm_fpu = "neon"`
- `arm_use_neon = true`

The 2025-12-16 Chromium change explicitly removed the old non-NEON ARM toggle.
That makes a maintained QtWebEngine ARM32 build incompatible with Tegra20's
no-NEON CPU unless a substantial downstream Chromium fork restores and
continually maintains a removed architecture configuration.

That maintenance burden is not justified here. Historical Chromium/QtWebKit
builds that still support VFPv3-D16 are not an acceptable fallback because the
task explicitly excludes stale vulnerable engine downgrades; qutebrowser itself
also warns against old QtWebKit and old distribution QtWebEngine security
baselines.

## Non-NEON feasibility

Debian's armhf architecture baseline is ARMv7 + Thumb-2 + VFPv3-D16, matching
Tegra20. This is a strong reason to use a private Debian armhf/glibc build root.

It is **not sufficient proof of a browser binary**. The repository already has
newer Firefox binaries that violate what the hardware can execute despite being
otherwise ARM32-compatible. WebKit 2.54 also integrates Skia, JSC, codecs and
third-party libraries whose per-target optimizations must be checked.

Required build flags/baseline for the successor are conceptually:

`-march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard`

but the acceptance gate is the produced artifact, not the requested flags:

- inspect ELF ARM attributes for every executable/shared object used by the
  browser;
- disassemble/audit for NEON/Advanced-SIMD and VFP d16-d31 usage;
- include bundled Skia/JSC/GStreamer/codec dependencies in the audit;
- run a CPU-only startup/JS qualification on Tegra20 before enabling any private
  GPU library;
- test JSC-generated code as well as static ELF code.

## Explicit unknowns

The following are intentionally **not** inferred from preserved EGL extension
strings or from a successful desktop trial:

- whether a current Debian armhf WPE 2.54 package/build is fully free of NEON
  and d16-d31 instructions;
- whether JSC JIT tiers emit only Tegra20-safe instructions;
- whether current Skia's GL backend behaves correctly on this Grate GLES2
  implementation under browser workloads;
- whether ANGLE/WebGL1 works on this stack;
- whether WebGL2 is possible (no ES3/GL3 proof exists);
- whether WPE GPU-process buffer exchange succeeds through GBM/DMA-BUF under
  the intended Wayland compositor path;
- whether Bubblewrap permits all required DRM/render-node access without
  weakening the sandbox;
- whether hardware video decode is available, performant or sandbox-accessible;
- whether the current system Mesa 26.2.3 Gallium mapping has any useful Grate
  capability. It was not qualified here and is not the accepted `68a…` driver;
- performance, memory pressure, thermals and power under a modern page workload.

## Serial successor plan

No live-device successor should begin until the preceding gate is accepted and a
separate mutation owner holds the relevant claim.

### Gate A — host-side current-engine build qualification

Build a reproducible **current WPE 2.54.x** Debian armhf/glibc bundle and a
private glibc Grate/Mesa overlay derived from the accepted source/fix set.

Acceptance:

1. exact source/package revisions and SHA-256s archived;
2. armhf/VFPv3-D16 target contract explicit;
3. no-NEON / no-d16-d31 audit passes across browser + relevant shared objects;
4. WPE/Cog or WPEPlatform launcher starts in a non-GPU host/qemu-style sanity
   environment where practical;
5. no device mutation.

Stop if the current 2.54 engine cannot be built cleanly for the CPU baseline.

### Gate B — separate serial device lane: private glibc Grate qualification

Only after Gate A and independent review, deploy the glibc Grate build under a
new hash-qualified private prefix/root. Do not replace `/usr/lib` Mesa and do
not alter default labwc.

Acceptance:

1. target CID/kernel preflight;
2. exact library hash and CPU attributes match Gate A;
3. no global mounts/config changes left behind;
4. rollback is deletion/unmount of the private root only.

### Gate C — sandbox-preserving EGL/GBM/DMA-BUF qualification

From the private browser environment, create only the minimum hardware context
needed to prove:

- vendor/renderer = Grate/Tegra, not llvmpipe/softpipe;
- expected GLES2/EGL extensions;
- GBM allocation and required DMA-BUF import/export/synchronization;
- zero GPU-fault/reset delta;
- sandbox prerequisites remain available.

This must run under the normal process/security model intended for the browser;
no `--no-sandbox`, root browser, or global device-permission workaround.

### Gate D — WPE first browser GPU trial

Use current WPE 2.54.x. Cog 0.18.x may be used as the compatibility harness,
but WPEPlatform/MiniBrowser should be kept as the forward-reference harness.

Prove separately:

1. HTTPS + JS;
2. static and JIT CPU safety;
3. GPU composition/rasterization using process maps plus objective GPU activity,
   not just a renderer string;
4. correct pixels/scroll/input under real pages;
5. Bubblewrap/userns/seccomp remain active;
6. WebGL1 only as a separate optional sub-gate;
7. media software decode, then V4L2 hardware decode as separate sub-gates;
8. fault/reset delta zero and clean teardown.

### Gate E — Firefox only after graphics requirement changes

Do **not** spend a device mutation cycle trying hardware WebRender with the
current GLES2-only accepted Grate capability.

Re-open Firefox GPU qualification only if:

- a reviewed driver exposes the GL feature/version level Firefox actually
  accepts;
- a maintained Firefox/ESR build passes the no-NEON/VFPv3-D16 CPU gate;
- sandbox is preserved.

The existing ESR140 software path remains recovery/reference throughout. A
maintenance update to final 140.17 could close the last ESR140 point-release gap
for that recovery image, but it would **not** restore ongoing ESR140 security
support.

### Gate F — independent review + hardware measurements

After a browser GPU trial passes, independently review:

- exact hashes and process/library provenance;
- sandbox state;
- rendered pixel correctness;
- GPU fault/reset logs;
- CPU load, browser PSS/RSS, GPU busy/frequency where observable;
- frame/scroll responsiveness;
- temperature/power over a longer soak;
- audio/video behavior;
- recovery path after browser exit and reboot.

Only then should a launcher/default-browser integration be considered.

## Recovery contract

Keep untouched until a reviewed successor passes:

- current pixman labwc default;
- `/opt/sl101-firefox-debian` Firefox ESR140 software recovery path;
- accepted `68a…` Grate artifacts as immutable provenance;
- system Mesa and boot/kernel configuration.

A software renderer is never reported as GPU success, and disabling browser
sandboxing is never accepted as a compatibility fix.

## Primary-source snapshot

See:

`work/sl101-browser-capability-20261003/upstream-requirements.md`

for the exact upstream URLs and 2026-10-03 source observations used above.
