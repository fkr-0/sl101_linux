# SL101 Cog/WPE pre-attach DMA-BUF readback candidate — 2026-11-05

## Result: implemented conditional exporter and bounded copy; NOT live-qualified

Isolated sources in `work/sl101-wpe-readback-20261105/`:
- `sl101-wpe-readback.{c,h}`: actual EGLImage DMA-BUF export API usage, metadata query, fd handling, linear layout bounds checks, explicit producer `sync_file` wait, DMA-BUF CPU START/END synchronization, read-only `mmap`, and immutable per-row copy. This **performs an actual copy** when supplied a valid producer sync_file FD and supported EGLImage. Returns `SL101_RB_NO_PRODUCER_FENCE` if no FD; failed/unknown paths do not read bytes.
- `0001-cog-wayland-producer-metadata-hook.patch`: independently applicable patch for the exact pinned source `work/scanout-followups-20261103/cog-teardown/cog-src/platform/wayland/cog-platform-wl.c`. It probes EGL-export metadata **before** `wl_surface_attach` but never invokes byte copying without a producer fence. Does not touch the release callback; real image pixel verification is therefore still BLOCKED.
- `source-identity.txt`: SHA256 of inspected Cog source.
- `tests/test_sl101_wpe_readback_candidate.py`: host-only compile, negative runtime, mock linear-copy, and zero-fuzz patch-apply checks.
- `readback_mock.c`: in-process mock EGL exporter, sync_file and dma-buf CPU-sync ioctls; exercises successful 4100-byte (non-64-aligned) pitch immutable copy, nonzero modifier rejection, and unsuccessful fence rejection. All EGL/DRM/sync responses are MOCKED, not actual SL101 evidence.

## Source and ABI basis

Pinned Cog callback source SHA256: `c78ea1a4e704b12a36fa1d3066d352d8aa949da35bbd8139dabe4ce3657d0ad4`. Existing Cog code exports EGLImageKHR via `on_export_wl_egl_image`, calls `eglCreateWaylandBufferFromImageWL` and attaches/commits. It does **not** provide a reliable producer-origin `sync_file` FD to the callback.

Mesa 25.0.7 `src/egl/drivers/dri2/egl_dri2.c` contains `dri2_export_dma_buf_image_query_mesa` and `dri2_export_dma_buf_image_mesa` implementation, including __DRI fourcc/plane/modifier queries and FD/stride/offset. This is **source capability only**, not proof that EGL_MESA_image_dma_buf_export is advertised by the actual Grate EGL display. The C code checks the complete extension token in `eglQueryString(display,EGL_EXTENSIONS)`, loads and checks both function pointers, and refuses invalid/unknown or nonzero modifiers. It cannot use ABI details until a device inventory verifies installed binaries.

The host has EGL headers with MESA export typedefs, pkg-config EGL version 1.5 and GLESv2 3.2. The host-only compiled helper is **x86-64**, linked with libEGL.so.1 and libc.so.6; it is not ARMHF and is not deployable onto the SL101. No code was installed on the tablet.

## Safety contract

1. The helper requires an **actual producer-supplied sync_file FD** that demonstrably covers all writes to the exact exported image. It checks fd poll readiness and `SYNC_IOC_FILE_INFO` with status=1 and at least one constituent fence, but these mechanical checks do not establish image association. A consumer-generated EGL fence or `glFinish` is **not** an acceptable substitute. No producer FD is available in existing Cog callback, so live byte readback cannot activate.
2. Only one plane, fourcc XRGB8888/ARGB8888, modifier exactly DRM_FORMAT_MOD_LINEAR (0), pitch >=4*width, offset>=0, and provable allocation size via dma-buf SEEK_END are accepted. No invented 64-byte pitch restriction. Overflow/oversized/short allocation fails closed; mmap failure fails closed; no unknown/tiled/compressed modifier mapping.
3. CPU access is bracketed by successful `DMA_BUF_IOCTL_SYNC` READ START/END. END errors reject the copy. Original exported FD is closed on every exit path; the borrowed image/display/fence are never destroyed by the helper.
4. The returned bytes are packed B,G,R,X/A rows with no padding (allocated `width*height*4`), with separate original pitch/offset/size metadata. They are meaningful only if external caller separately certifies fence provenance and exact frame ID, and the GPU/kernel's coherent DMA-BUF mapping model. The helper's result is named `OK_CONDITIONAL` intentionally.
5. The metadata patch must be compiled together with the helper by an ARMHF crossbuild into a **private** Cog prefix. It has not been compiled as part of Cog; its expected source-relative include path needs build integration and exact WPE FDO/EGL ABI qualification. It is not an approved production patch.
6. The existing Cog teardown reentrant UAF remains HOLD. The separate readback helper must not be merged with or used as justification for unsafe teardown edits.

## Device gates: not cleared

Earlier SSH confirmed `sl101-nura` and `7.0.1-postmarketos-grate`, but the first `mmcblk0` CID differed from the previously documented SD CID and must be correctly attributed before mutation. The expanded read-only EGL/device inventory attempt was blocked by an execution safety check; this worker **did not retry by an alternative route**. Consequently installed EGL export support, image modifier, producer fence availability, exact armhf ELF/DT_NEEDED and on-device readback are all unverified.

**Live test = BLOCKED** until approved read-only inventory, proven producer fence handoff (or other independently validated kernel/driver producer completion), different-author safety review, private ARMHF build and independently supervised 15s graphics owner/watchdog/rollback. The separate LLM reviewer operation was unavailable at the tool layer, so **no independent review has been obtained**. Host mock correctness is not a substitute. No browser, labwc or device process was started or killed; no Pixman config touched.

The pre-existing 71,067 wrong ROI pixels and 22,232 magenta pixels are **screen-space** findings only. Do not attribute corruption to WPE or Grate from this candidate.

## Host commands

    python3 -m unittest tests.test_sl101_wpe_readback_candidate -v
    make test
    make check

Once producer-fence origin is solved, extend on-device tests to prove immutable snapshot before attach and correlated frame marker against the same labwc screenshot. Never claim a producer pixel verdict from successful EGL export alone.
