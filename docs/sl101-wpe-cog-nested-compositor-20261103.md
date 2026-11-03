# SL101 Cog/WPE nested Wayland DMA-BUF format advertisement — source audit

Date: 2026-11-03
OCP task: SL101-LINUX-03-WPE-COG-NESTED-COMPOSITOR-20261103-8064BD
Dispatch attempt: 81c65c4172894c8ab9cc1a4992a35d9c
Scope: source and preserved host evidence only; NO live SL101 graphics or device mutation.

## Executive verdict

**Verified:** In the Cog 0.18.5 legacy Wayland backend, Cog connects to labwc as an ordinary outer Wayland client. It passes its initialized outer Wayland-backed EGLDisplay to WPEBackend-fdo 1.16.1. WPEBackend-fdo itself creates an independent, private Wayland server for the WebKit renderer process and advertises DMA-BUF capabilities derived from EGL extension and format queries on that EGLDisplay. The outer compositor's Wayland registry/format/modifier events are **not** directly copied into the nested server.

**Verified:** WPEBackend-fdo 1.16.1 announces zwp_linux_dmabuf_v1 version 4 with a default-feedback format table, populated through eglQueryDmaBufFormatsEXT and eglQueryDmaBufModifiersEXT. Its get_surface_feedback callback is, however, an empty stub. Upstream issue #207 and open PR #208 identify the resulting protocol invalid-object regression on surface-feedback destruction. The version shipped in the SL101 browser bundle is exactly 1.16.1-1+b1.

**Inference, not yet device-proven:** An entirely empty format bitmap at the Mesa EGL WebProcess client may mean (a) EGL's queried format list was empty, (b) a missing/invalid feedback format table/device/tranche, (c) the relevant DMA-BUF protocol global was not created due to missing EGL extensions, or (d) a mismatch between advertised version and Mesa's event handling. Treat WPEBackend-fdo as the principal source to instrument, not Cog's outer registry forwarding. This does not on its own exonerate Mesa or Grate.

## Versions and local provenance

- Cog: 0.18.5-1
- WPE WebKit: 2.54.0-2
- WPEBackend-fdo: 1.16.1-1+b1
- Host evidence: work/sl101-cog-wpe-20261003/glibc-build/pkginstall.log (download/unpack/setup lines), work/sl101-cog-wpe-20261003/software-smoke-sandboxed-final.json (versions field).
- Relevant local accepted Grate capability baseline: docs/sl101-browser-capability-20261003.md (EGL 1.4, EGL DMA-BUF import/modifiers, EGL_WL_bind_wayland_display, GLES2). This is **not** proof that every extension and format query succeeds inside the deployed WPE process.

## Connections and ownership

    labwc / outer Wayland server
             |
             | (A) Cog wl_display_connect(NULL) and eglGetDisplay(outer wl_display)
             v
    Cog 0.18.5 (Wayland platform) --- EGLDisplay ---> WPEBackend-fdo ImplEGL
             |                                              |
             | export EGLImage -> wl_buffer (outer)           | wl_display_create()
             |                                              | socketpair + wl_client_create()
             v                                              v
    outer Wayland surface                             private Wayland server
                                                            ^
                                                            | (B) wl_display_connect_to_fd(hostFD)
                                                            |
                                                WebKit renderer / Mesa EGL

(A) and (B) are **different Wayland connections**. Each advertises its own protocol globals and format information. For Cog DRM, (A) is replaced with GBM/KMS rather than an outer compositor, but (B) still exists.

## Source walkthrough (version-pinned)

### 1. Cog Wayland platform: outer connection and EGL display

File: https://github.com/Igalia/cog/blob/0.18.5/platform/wayland/cog-platform-wl.c

- init_wayland(), lines 2024-2044: wl_display_connect(NULL), wl_display_get_registry, wl_registry_add_listener, roundtrip. This is the labwc connection.
- registry_global(), lines 778-845: binds ordinary outer globals. The zwp_linux_dmabuf_v1 binding is under COG_ENABLE_WESTON_DIRECT_DISPLAY and requests version 3; it is not a nested Wayland-server format-forwarding routine.
- init_egl(), lines 2187-2206: eglGetDisplay((EGLNativeDisplayType) wl_data.display) and eglInitialize.
- platform initialization, line 2547: wpe_fdo_initialize_for_egl_display(egl_data.display); get_view_backend(), lines 2593-2613, creates wpe_view_backend_exportable_fdo_egl and passes it to WebKit.
- on_export_wl_egl_image(), lines 1691-1750: uses eglCreateWaylandBufferFromImageWL(egl_data.display, exported EGLImage), wl_surface_attach, and wl_surface_commit on the **outer** Cog surface. This is downstream presentation, not source of nested DMA-BUF negotiation.

### 2. Cog DRM: GBM direct rather than an outer Wayland EGLDisplay

File: https://github.com/Igalia/cog/blob/0.18.5/platform/drm/cog-platform-drm.c

- init_gbm(), lines 667-675: gbm_create_device(drm_data.fd).
- init_egl(), lines 689-713: eglGetPlatformDisplayEXT(EGL_PLATFORM_GBM_KHR, GBM device) or eglGetDisplay(GBM device), then eglInitialize.
- Platform initialize at line 1496 calls wpe_fdo_initialize_for_egl_display on this GBM-backed EGLDisplay.
- DRM GLES renderer https://github.com/Igalia/cog/blob/0.18.5/platform/drm/cog-drm-gles-renderer.c uses gbm_surface_lock_front_buffer and drmModeAddFB2WithModifiers/FB2 for KMS scan-out, lines 71-127. Its output mode is different from Cog's Wayland output, but WPEBackend-fdo's renderer IPC remains separate.

### 3. WPEBackend-fdo constructs the nested Wayland server

- https://github.com/Igalia/WPEBackend-fdo/blob/1.16.1/src/initialize-egl.cpp#L34-L40 — wpe_fdo_initialize_for_egl_display() constructs a singleton WS::Instance with WS::ImplEGL and initializes the EGL display.
- https://github.com/Igalia/WPEBackend-fdo/blob/1.16.1/src/ws.cpp#L412-L451 — WS::Instance::Instance uses wl_display_create(), registers wl_compositor, wpe_bridge, wpe_dmabuf_pool_manager, and integrates its event loop.
- https://github.com/Igalia/WPEBackend-fdo/blob/1.16.1/src/ws.cpp#L495-L509 — WS::Instance::createClient() creates socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC), calls wl_client_create on the private server, returns the duplicated other end to WebKit's rendering process.
- https://github.com/Igalia/WPEBackend-fdo/blob/1.16.1/src/ws-client.cpp#L120-L135 — WS::BaseBackend::BaseBackend(hostFD) connects with wl_display_connect_to_fd(hostFD), NOT wl_display_connect(NULL).
- https://github.com/Igalia/WPEBackend-fdo/blob/1.16.1/src/egl-client-wayland.cpp#L35-L66 — BackendWayland::nativeDisplay() returns that private wl_display and TargetWayland creates a wl_egl_window for the renderer.
- https://github.com/Igalia/WPEBackend-fdo/blob/1.16.1/src/renderer-backend-egl.cpp#L40-L95 — chooses the Wayland target or custom DMA-BUF pool implementation according to the internal bridge's implementation type.

### 4. Nested DMA-BUF advertisement originates in EGL queries

File: https://github.com/Igalia/WPEBackend-fdo/blob/1.16.1/src/ws-egl.cpp

- ImplEGL::initialize(), lines 114-173, checks EGL_WL_bind_wayland_display, EGL_KHR_image_base, EGL_EXT_image_dma_buf_import, EGL_EXT_image_dma_buf_import_modifiers, initializes wl_shm, and optionally calls eglBindWaylandDisplayWL.
- **Critical gate, lines 166-173:** Only when BOTH DMA-BUF import extensions are present does it call initMainDevice(), initFormatTable(), and linux_dmabuf_setup(display()). It does not unconditionally offer the global.
- foreachDmaBufModifier(), lines 301-329: calls eglQueryDmaBufFormatsEXT on Cog's passed EGLDisplay (array max 128) and eglQueryDmaBufModifiersEXT per format (array max 64). If modifiers are absent, emits DRM_FORMAT_MOD_INVALID for a known format. If the queried number of formats is zero, emits none.
- initMainDevice(), lines 332-365: queries EGL device metadata (EGL_EXT_device_query, EGL_EXT_device_drm, EGL_DRM_DEVICE_FILE_EXT) and obtains dev_t from stat(). Several early-return paths leave the mainDevice array empty; actual SL101 behavior remains unverified.
- initFormatTable(), lines 367-423: places the (format, modifier) tuples into a memfd-backed 16-byte-entry table and constructs tranche indices. The zero-format case computes a zero-sized mapping and can fail to materialize a valid table: audit this exact path on the installed binary.
- createImage(linux_dmabuf_buffer), lines 187-244: imports received WebProcess DMA-BUF planes via eglCreateImageKHR(EGL_LINUX_DMA_BUF_EXT). It is not a GBM allocator or a Wayland registry-forwarding function.

### 5. Protocol version split, 1.16.0 vs 1.16.1

File: https://github.com/Igalia/WPEBackend-fdo/blob/1.16.0/src/linux-dmabuf/linux-dmabuf.cpp#L353-L399

- 1.16.0: linux_dmabuf_setup advertises zwp_linux_dmabuf_v1 **version 3**; bind_linux_dmabuf iterates EGL-derived formats and sends legacy modifier events (or format events for older clients).

File: https://github.com/Igalia/WPEBackend-fdo/blob/1.16.1/src/linux-dmabuf/linux-dmabuf.cpp#L352-L455

- 1.16.1: advertises **version 4**, sends default_feedback with format_table, main_device, tranche_target_device, tranche_flags, tranche_formats, tranche_done, done. It still sends legacy modifier events in bind_linux_dmabuf, but clients implementing v4 may use feedback rather than those deprecated events.
- **Verified regression:** linux_dmabuf_get_surface_feedback(), lines 399-405, is a no-op despite the advertised request. Mesa creates a feedback object for a surface and later destroys it, yielding an invalid object/protocol disconnect (upstream issue #207). The proposed remediation is upstream PR #208, **open and not merged as checked on 2026-11-03**.
- WPEBackend-fdo release notes: https://wpewebkit.org/release/wpebackend-fdo-1.16.1.html .
- Source PR adding v4 default feedback: https://github.com/Igalia/WPEBackend-fdo/pull/202 .
- Regression: https://github.com/Igalia/WPEBackend-fdo/issues/207 .
- Proposed fix: https://github.com/Igalia/WPEBackend-fdo/pull/208 .

## WebKit source, and the WPEPlatform distinction

Official current WebKit source:
- https://github.com/WebKit/WebKit/blob/main/Source/WebKit/WPEPlatform/wpe/wayland/WPEDisplayWayland.cpp — this newer architecture binds an outer Wayland linux-dmabuf v4 global, receives feedback/device information and has get_preferred_buffer_formats. Its current source code includes callback stubs for some feedback fields; this is not proof of the SL101 legacy backend's behavior.
- https://github.com/WebKit/WebKit/blob/main/Source/WebKit/WPEPlatform/wpe/wayland/WPEViewWayland.cpp — renders WPEBufferDMABuf by creating a zwp_linux_buffer_params_v1 and attaching a wl_buffer, with an eglCreateWaylandBufferFromImageWL fallback path.
- https://github.com/WebKit/WebKit/blob/main/Source/WebKit/WPEPlatform/docs/migration-mapping.md — the legacy WPEBackend-fdo/libwpe renderer EGL target is removed in the new WPEPlatform API, superseded by buffer sharing, WPEView, and WPEBuffer. **Do not attribute WPEPlatform code to Cog 0.18.5's fdo path.** The available contemporary WebKit source is main, not necessarily the exact installed 2.54.0 source revision.

## Known related incidents (not exact-device proof)

- https://github.com/Igalia/WPEBackend-fdo/issues/207 — confirmed 1.16.1 empty surface-feedback handler, invalid-object disconnect.
- https://github.com/Igalia/WPEBackend-fdo/pull/208 — proposed targeted fix for that separate regression.
- https://github.com/Igalia/cog/issues/774 — Cog renderer EGL_NOT_INITIALIZED after Mesa 25.2.0+, similar symptom but no proof of identical root cause.
- https://github.com/Igalia/cog/issues/738 — transition from eglCreateWaylandBufferFromImageWL to DMA-BUF, another compatibility seam.
- https://github.com/Igalia/cog/issues/604 — external compositor-specific EGL_NOT_INITIALIZED / failed DMA-BUF import.
- https://github.com/Igalia/cog/issues/557 — failed to import supplied DMA-BUFs with an outer compositor; not the same as empty nested format feedback.

## Local Mesa patch 0031: what it establishes and what it does not

Existing untracked file: patches/mesa-25.0.7/0031-egl-wayland-accept-driver-formats-when-server-bitmap-empty.patch

The patch proposes bypassing Mesa's server_supports_format() filtering when the entire server format bitmap is empty but fd_render_gpu >= 0, thereby attempting to use driver-supported formats even with no server advertisement. This is a **workaround, not evidence that the nested Wayland server actually imports every proposed format**. A render-node fd or main_device does not prove the compositor can import every driver's format/modifier and does not satisfy protocol feedback requirements by itself. It may restore EGLConfig enumeration while leaving actual DMA-BUF creation/attachment unsupported. The patch is untracked and was NOT applied, changed, built, promoted, or deployed by this research lane.

## Root-cause hypotheses and discriminating evidence

| Hypothesis | Status | Distinguishing evidence |
|---|---|---|
| Cog failed to copy labwc's wl_dmabuf format list | **Contradicted as architecture premise** | No protocol event passthrough is present; WPEBackend-fdo is owner of private globals and EGL-derived list |
| WPEBackend-fdo global absent on device | Plausible | Check extensions exposed to ImplEGL and private wl_registry.global events |
| EGL format query on Cog's EGLDisplay yields zero | Plausible | Instrument eglQueryDmaBufFormatsEXT count, then per-format/modifier results |
| v4 feedback table invalid/empty or missing tranche | Plausible | Trace get_default_feedback, format_table fd/size, tranche_formats, main_device and Mesa's bitmap population |
| Known 1.16.1 surface feedback object bug | **Verified in source** | Look for get_surface_feedback followed by destroy and invalid object; normally a subsequent, distinct failure after EGL initialization |
| Grate/Mesa config filtering too strict | Plausible, conditional | Compare Mesa pre-patch EGLConfig counts and error path to exact protocol trace; ensure any workaround passes actual wl_buffer import tests |

## Qualification sequence (under existing device lock only)

1. Preserve exact versions, EGL extension lists and actual EGLDisplay selection on the SL101. Do not mutate labwc or global/system Mesa.
2. Collect a bounded WAYLAND_DEBUG=1 trace from the WebKit renderer process's private Wayland FD connection. Distinguish it from Cog's outer labwc connection. Record global advertised version and bind version.
3. Check both paths: v3 legacy modifier events versus v4 get_default_feedback / format_table / tranche_formats. Verify returned format-table size and main_device/tranche device validity.
4. Instrument WPEBackend-fdo ImplEGL::foreachDmaBufModifier to distinguish EGL query count zero from feedback transport/parsing zero.
5. Compare Mesa's resulting supported formats bitmap, EGLConfig count, eglInitialize outcome, and a real DMA-BUF wl_buffer import/attach acknowledgment (not merely EGL initialization).
6. Separately exercise a view-create / destroy / view-create sequence to expose issue #207; do not assume PR #208 has shipped in 1.16.1-1+b1.
7. Promote no patch as default until buffer pixels and frame lifecycle, GPU fault delta, and software fallback all qualify. Maintain serial ownership of the tablet.

## Limitations

Source files at Cog 0.18.5 and WPEBackend-fdo 1.16.0/1.16.1 were fetched and inspected, along with current official WebKit WPEPlatform files. No SL101 EGL format query, WAYLAND_DEBUG trace, compositor protocol capture, pixel render, deployment, or real-device test was performed here. This task establishes the architecture and code-level fault candidates, not a final on-device root-cause proof.
