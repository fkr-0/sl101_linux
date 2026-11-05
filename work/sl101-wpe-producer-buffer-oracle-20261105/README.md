# WPE producer-buffer oracle — host-only candidate, 2026-11-05

## Evidence boundary

The 2026-11-04 screen-space oracle reports 71,067/737,280 wrong pixels,
including 22,232 exact magenta pixels, and zero changing ROI pixels between
two GPU captures. Its stage is `screencopy-after-compositor`; it **does not**
verify WPE producer pixels. Software Cog was nearly black and cannot serve as
a comparative reference. No producer correctness or ARMHF build is claimed.

## Verified source hooks and lifetime

Inspected Cog source:
`work/scanout-followups-20261103/cog-teardown/cog-src/platform/wayland/cog-platform-wl.c`.
The actual export callback is `on_export_wl_egl_image` (near line 1691),
registered in `cog_wl_platform_get_view_backend` (near line 2594).
Cog checks image dimensions, stores its WPE EGL image, calls
`eglCreateWaylandBufferFromImageWL`, registers `buffer_listener`, attaches
the wl_buffer with `wl_surface_attach`, then commits. In
`on_buffer_release` (near line 1648), Cog dispatches
`wpe_view_backend_exportable_fdo_egl_dispatch_release_exported_image` and
destroys the corresponding wl_buffer. A frame callback/commit does **not**
substitute for a GPU fence or wl_buffer.release.

Do not read image/BO memory after the release dispatch; do not infer an image's
plane metadata from the EGL image pointer or wl_buffer pointer. The reviewed
callback exposes width/height and EGLImageKHR, but does not itself establish
DRM fourcc, modifier, offsets, pitches, dma-buf fds, plane count, or an
independent fence. Those require an ABI-verified EGL_MESA_image_dma_buf_export
query/export path or an equivalent WPE-side producer API, and extension
availability must be checked at runtime against the exact pinned EGL display.
Do not guess fourcc/modifier or treat unsupported exports as linear.

## Proposed isolated instrumentation (not yet applied to Cog)

1. On `on_export_wl_egl_image` assign a monotonically increasing frame_id and
   append a timestamped export event with width, height, EGL image handle only
   as an ephemeral debug identifier (never durable producer identity).
2. Query exporter support, metadata and plane geometry; record exact DRM
   fourcc, modifier (including high/low words), planes' offset/pitch, and
   duplicated fd identity when supported. Treat absent metadata as unknown,
   not zero/linear. Validate per-plane dimensions (including chroma
   subsampling) against the fourcc; the host oracle currently **rejects**
   all multi-plane formats by design.
3. Only for explicitly verified linear XRGB8888/ARGB8888 with a documented
   mapping path: obtain a valid synchronization completion covering writes,
   and copy pixels to separately owned immutable memory **before** release.
   Neither EGL export nor a CPU mmap implies completed rendering. If fences,
   mapping, modifier, ownership or coherency cannot be proven, record
   `readback=unavailable` and **skip pixel comparison**.
4. Log `wl_surface_attach`, `wl_surface_commit`, frame callback, buffer
   release and WPE release dispatch using frame_id keyed by **each wl_buffer**.
   Do not use the global mutable `wpe_view_data.image` for delayed callbacks.
   Never reuse a released identifier as if it were an immutable pixel sample.
5. Record producer bytes' SHA256 and per-pixel oracle *only after*
   authenticated readback. Use the same 1024x720 static pattern and account
   for DRM memory byte order (XRGB8888 on little-endian commonly B,G,R,X),
   X alpha semantics, surface scaling, transform and crop. Preserve the raw
   snapshot/hash for provenance and compare only identical frame IDs.
6. Cross-build private ARMHF Cog candidate only after confirming
   WPE FDO/EGL header versions and symbols match the device sysroot; record
   compiler triplet, source SHA256, `readelf -h`, `readelf -d` DT_NEEDED and
   `readelf -Ws` relevant ABI symbols. No deployment is authorized here.

## Host gate and expected evidence

`python3 -m unittest discover -s work/sl101-wpe-producer-buffer-oracle-20261105 -p 'test_*.py' -v`

| Fixture | Expected outcome |
| --- | --- |
| Correct linear XRGB8888 geometry + proven caller-provided snapshot | metadata accepted; SHA256 returned; producer verification **false** |
| Pitch 28 for width 8 / 32 minimum | `mismatched_pitch` |
| Release sequence earlier than attach | `stale_release` |
| Two planes supplied to single-plane XRGB gate | `unsupported_plane_count` |
| Tiled/unsupported modifier | `unsupported_or_unknown_modifier` |
| Fence unproven | `unsynchronized_readback` |
| Snapshot acquisition before release unproven | `snapshot_not_proven_before_release` |

This library checks assertions on declared metadata and bytes; fixture results
cannot establish actual Cog producer bytes, and neither frame ID nor hash alone
proves that the content is correct.

## Next independent comparison (requires separately authorized graphics lane)

Capture one known static frame on WPE's producer side before attach, with a
provable synchronization barrier and fully specified layout, then capture labwc
output of the same on-screen frame. Correlate using a unique visually encoded
frame marker and export/attach/release event IDs, preserving both raw image
hashes and geometry. Check producer oracle first:

- Producer wrong, compositor wrong: producer/WPE render or export path.
- Producer correct, compositor wrong: labwc/Grate import/sampling/composition.
- Both correct, panel wrong: scanout/display path.
- Producer not safely readable, or identity cannot be correlated: **inconclusive**.

No live browser, compositor, tablet, Mesa source, deployment, reboot, or
graphics configuration changed by this candidate.
