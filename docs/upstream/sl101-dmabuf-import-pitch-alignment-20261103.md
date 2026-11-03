# DMA-BUF import pitch / alignment: Mesa comparison and SL101 handoff

Research date: 2026-11-03
Canonical OCP task: SL101-LINUX-07-DMABUF-IMPORT-PITCH-ALIGNMENT-20261103-C90190
Scope: read-only inspection of Wayland/DRM contracts, the local Grate Mesa 25.0.7 source, and a public Mesa source mirror. No device or graphics-session mutation, code patch, or GPU claim.

## Decision summary

1. A dma-buf file descriptor is not a self-describing universal pitch/format/modifier descriptor. The exporter conveys each plane's fd, byte offset, stride (bytes/row) and modifier through Wayland linux-dmabuf or an equivalent import API. Width, height, FourCC and flags are also communicated.
2. An importer is entitled to reject incompatible layouts. Gallium's `resource_from_handle` receives a `winsys_handle` with the caller-provided stride and modifier; it does not confer arbitrary-stride compatibility.
3. The Wayland feedback contract publishes preferred devices and *format/modifier pairs*, not arbitrary numeric row-stride alignment. Even a correctly advertised pair can fail at allocation/import due to allocation-specific constraints.
4. Drivers differ substantially: etnaviv checks minimum padded pitch/BO size; Lima distinguishes tiled exact pitch from flexible linear minimum; Panfrost validates per-modifier constraints; freedreno validates effective pitch; the inspected NV50 nouveau path preserves external pitch and BO tiling configuration.
5. On this local Grate tree, `grate_screen_resource_from_handle` assigns `resource->pitch = handle->stride` but does not inspect `handle->modifier` or validate the pitch for sampling; `grate_create_sampler_view` later rejects anything other than `align(width * blocksize, 64)`. An imported fd can therefore succeed *before* failing when used as a texture. That is an observed local implementation seam, not proof of the physical Tegra20 pitch requirement.

## 1. Protocol contract and negotiation

### Metadata

The Wayland `zwp_linux_buffer_params_v1.add` request sends:

~~~c
add(fd, plane_idx, offset, stride, modifier_hi, modifier_lo);
~~~

All planes are described explicitly. `offset` and `stride` are in bytes. `create`/`create_immed` supplies width, height, DRM FourCC and flags; `create` can report failure. A dma-buf fd alone identifies the shared allocation and does not provide a universal, reliable way to query a row-stride or image format.

Starting at linux-dmabuf v4, the old `format` and `modifier` events are replaced by default/surface feedback: main/preferred device, format table, tranche targets/flags/formats and `done`. Tranches are ordered by preference. In v6 there are additional sampling-tranche semantics. There is **no pitch-alignment field**. Even a supported pair needs an appropriately allocated buffer; scanout additionally has display-plane/DRM constraints.

Linux KMS modifiers are opaque *layout* identifiers that can impose minimum pitch/alignment rules. The kernel docs explicitly prohibit inventing distinct modifiers that differ only by pitch-alignment class because an aligned buffer could match several aliases. Modifiers are not a general pitch-alignment negotiation API.

Sources:
- Wayland linux-dmabuf-v1 protocol: https://wayland.app/protocols/linux-dmabuf-v1
- Linux kernel KMS modifiers contract: https://cdn.kernel.org/doc/html/latest/gpu/drm-kms.html
- Linux drm_fourcc.h modifier comments: https://github.com/torvalds/linux/blob/master/include/uapi/drm/drm_fourcc.h

### Important outcomes

- Import success is not guaranteed merely by a valid fd or format/modifier advertisement.
- Importers should consume the declared stride and reject an impossible layout, **not silently change the pitch**.
- For a client with multiple possible allocators, choose the allocator/device/modifier from feedback and verify its produced pitch. The protocol alone cannot command `align(stride,64)`.
- `DRM_FORMAT_MOD_INVALID` means an implicit/unspecified modifier, not a promise that every implementation will treat the image as linear. Some driver import paths map it to linear; other implementations may use sideband kernel layout information. Prefer explicit `DRM_FORMAT_MOD_LINEAR` for cross-driver linear sharing when supported.
- Feedback changes can cause buffer reallocation; they are not instructions for rewriting pitch on an existing BO.

## 2. Mesa path: DRI-to-Gallium

Local source: `build/mesa-grate-clean/mesa-25.0.7/src/gallium/frontends/dri/dri2.c`:

- `dri2_from_dma_bufs` (near line 1567) validates format/number of planes and forms a `struct winsys_handle` per input:
  - `type = WINSYS_HANDLE_TYPE_FD`
  - `handle = fds[i]`
  - `stride = strides[i]`
  - `offset = offsets[i]`
  - `modifier = modifier`
  - `plane = i`
- `dri_create_image_from_winsys` (near lines 984/1007) calls `pscreen->resource_from_handle(pscreen, &templ, &whandle[i], ...)` for the image/planes.
- Import failures return NULL up the chain. A subsequent successful `wl_buffer` presentation still depends on actual rendering, sampling, synchronization and optionally scanout.

Public mirror for shared frontend: https://github.com/chaotic-cx/mesa-mirror/blob/main/src/gallium/frontends/dri/dri2.c

Note: compositor-specific wl_buffer import may enter another path (direct DRM planes, GBM, renderer helpers, etc.). Record which path is actually taken before attributing a failure to this particular function.

## 3. Driver-by-driver source findings

All cited Mesa source is a public mirror's `main` branch inspected 2026-11-03, **not** a pinned Mesa upstream release tag; behavior can differ by generation and release.

| Driver | File / function | What import does with pitch | Rejection mechanism | Fixed universal alignment? |
|---|---|---|---|---|
| etnaviv | `src/gallium/drivers/etnaviv/etnaviv_resource.c::etna_resource_from_handle` | Takes `handle->stride` verbatim. Uses `etna_layout_multiple` to determine width/height padding. | Rejects if stride below padded-width format stride or `bo_size < stride * padded_height`; tracks render compatibility. | No; depends on format, layout and hardware. |
| lima | `src/gallium/drivers/lima/lima_resource.c::lima_resource_from_handle` | Takes `handle->stride`. Computes expected 16-pixel-padded row stride. | Sampler/RT/depth input offset must be multiple of 64 bytes; tiled ARM 16×16 stride must equal computed pitch; linear RT/depth pitch below minimum rejected, non-8-byte alignment warns but does not itself reject; BO-size checked. | 64-byte **offset** for selected uses; tiled exact pitch; linear import not globally pitch64. |
| panfrost | `src/gallium/drivers/panfrost/pan_resource.c::panfrost_resource_from_handle`, `strict_import` | Passes `offset_B` and `wsi_row_pitch_B` to `panfrost_resource_init_image` / `pan_image_layout_init` along with modifier-dependent `strict`. | Invalid constraints/layout return false and destroy imported resource; import of BO itself may also fail. Historical relaxed checks for some AFBC/AFRC/MTK modifiers; linear and U-tiled are strict. | No one pitch multiple for all formats/modifiers/generations. |
| freedreno | `src/gallium/drivers/freedreno/freedreno_resource.c::fd_resource_from_handle`, `fd_layout_resource_for_handle` | Builds a layout from external pitch/offset. Generic linear path sets `layout.pitch0 = handle->stride`. | Checks width minimum and computed/validated pitch, fails layout helper on unsupported modifier, then explicitly rejects `layout.pitch0 != handle->stride`. UBWC paths use their specialized layout validation. | No; `gmem_align_w`, bpp, generation and modifier matter. |
| nouveau NV50 | `src/gallium/drivers/nouveau/nv50/nv50_miptree.c::nv50_miptree_from_handle`, `nouveau_screen_bo_from_handle` | Gets actual stride through import helper and assigns it to `level[0].pitch`; reads BO tile mode from `bo->config.nv50.tile_mode`. | Rejects unsupported resource shape or BO import failure. No separate unconditional imported-pitch modulus check visible in this NV50 function; other hardware/users can still reject. | No universal imported-pitch rule demonstrated by this function. |

Code details:

### etnaviv

~~~c
level->stride = handle->stride;
etna_layout_multiple(screen, tmpl, rsc->layout,
                     &paddingX, &paddingY, &rsc->halign);
level->padded_width = align(level->width, paddingX);
level->padded_height = align(level->height, paddingY);

if (level->stride < util_format_get_stride(tmpl->format,
                                           level->padded_width))
    goto fail;
if (etna_bo_size(rsc->bo) < level->stride * level->padded_height)
    goto fail;
~~~

The imported stride can be larger than the producer's normal preferred pitch. This is only valid when the hardware path can actually use that pitch.

Source: https://github.com/chaotic-cx/mesa-mirror/blob/main/src/gallium/drivers/etnaviv/etnaviv_resource.c

### lima

~~~c
/* Sampler/RT/depth offset constraint, not a generic pitch rule */
if (handle->offset & 0x3f)
    return NULL;

/* For render/depth/tiled resources */
stride = util_format_get_stride(pres->format, align(pres->width0, 16));

if (res->tiled && res->levels[0].stride != stride)
    goto err_out;
if (!res->tiled && (res->levels[0].stride % 8))
    fprintf(stderr, "linear imported buffer stride is not aligned ...");
if (!res->tiled && res->levels[0].stride < stride)
    goto err_out;
~~~

The non-eight-aligned case logs a warning **without jumping to err_out** in the inspected source. Do not turn a warning into a claimed rejection.

Source: https://github.com/chaotic-cx/mesa-mirror/blob/main/src/gallium/drivers/lima/lima_resource.c

### panfrost

~~~c
struct pan_image_layout_constraints explicit_layout = {
    .offset_B = whandle->offset,
    .wsi_row_pitch_B = whandle->stride,
    .strict = strict_import(dev, mod, templat->format),
};

bool valid = panfrost_resource_init_image(pscreen, rsc, &iprops,
                                           whandle->plane,
                                           &explicit_layout);
if (!valid)
    return NULL; /* after cleanup */
~~~

Actual detailed alignment is handled downstream by Panfrost's image-layout machinery, not by a hardcoded rule in the importer.

Source: https://github.com/chaotic-cx/mesa-mirror/blob/main/src/gallium/drivers/panfrost/pan_resource.c

### freedreno

~~~c
if (!screen->layout_resource_for_handle(rsc, handle))
    goto fail;
if (rsc->layout.pitch0 != handle->stride)
    goto fail;
~~~

In `fd_layout_resource_for_handle`, the linear helper checks `handle->stride >= width * cpp` and that the driver-computed pitch agrees, after setting GPU-dependent pitch alignment. Exact imported pitch identity is deliberately validated, not repaired by rounding the declared pitch.

Source: https://github.com/chaotic-cx/mesa-mirror/blob/main/src/gallium/drivers/freedreno/freedreno_resource.c

### nouveau NV50

~~~c
mt->base.bo = nouveau_screen_bo_from_handle(pscreen, whandle, &stride);
if (!mt->base.bo)
    return NULL;
mt->level[0].pitch = stride;
mt->level[0].tile_mode = mt->base.bo->config.nv50.tile_mode;
~~~

This illustrates use of existing external BO metadata without force-aligning the imported pitch, but is **not** a universal Nouveau compatibility guarantee. NV50 is not Tegra20's graphics hardware.

Sources:
- https://github.com/chaotic-cx/mesa-mirror/blob/main/src/gallium/drivers/nouveau/nv50/nv50_miptree.c
- https://github.com/chaotic-cx/mesa-mirror/blob/main/src/gallium/drivers/nouveau/nouveau_screen.c

## 4. SL101-specific Grate source observations

Local generated Mesa 25.0.7 Grate source (`build/mesa-grate-clean/mesa-25.0.7`), not an independently pinned upstream Grate commit:

- `src/gallium/drivers/grate/grate_resource.c::grate_screen_resource_from_handle`:
  - For FD import, rejects nonzero `handle->offset`.
  - Calls `drm_tegra_bo_from_dmabuf`, checks result.
  - Assigns `resource->pitch = handle->stride`.
  - Does **not** inspect `handle->modifier` and does **not** validate pitch against the width/usage on this path.
- `src/gallium/drivers/grate/grate_resource.c::grate_screen_resource_create`:
  - For render target/scanout, allocates with 64-byte row alignment; for depth, 256 bytes.
  - For sampler-view allocations, currently uses 64-byte alignment.
- `src/gallium/drivers/grate/grate_state.c::grate_create_sampler_view`:
  - Rejects tiled resource or `resource->pitch != align(width * blocksize, 64)`.
  - Therefore FD import can succeed but later sampler-view creation can return NULL for imported BOs with incompatible pitch.
- `src/gallium/drivers/grate/grate_state.c` render-target setup programs an explicit pitch register; sampled-texture descriptors may have separate pitch restrictions. Do not assume render-target compatibility establishes sampler compatibility.

The local `patches/mesa-25.0.7/0033-grate-fix-texture-pitch-alignment-64-byte.patch` asserts Tegra20 sampler-derived 64-byte pitch from observations at widths 300/320 px RGBA. Those two widths alone distinguish 16 from 32/64 alignment, *not* 32 from 64 (as already noted in `docs/upstream/grate-mesa-submission-split-20261103.md`). Other local historical mipmap allocations use pitch16. Treat 64 as a **local hypothesis/restriction** requiring row oracle/pixel testing and a complete allocation/import/mip-level contract before upstream promotion.

The local EGL failure/Wayland-format bitmap investigation is a distinct issue: missing format/modifier feedback can prevent selection of a buffer even before fd/stride import. Do not treat successful EGL initialization or mapping private Grate libraries as proof of correct pixels or browser frame presentation.

## 5. What to do when client and compositor disagree

Preferred sequence:

1. Capture client's actual `DRM FourCC / modifier / width / height / plane fds / offsets / strides / BO size`. Record the Wayland global version and default/surface feedback `format_table`, tranches, `done`, target/main devices. Include client and compositor GPU/render-node identities and import API error/screen logs.
2. Establish which path fails: no advertised compatible pair; format selection; buffer allocation; `create`/`create_immed`; importer `resource_from_handle`; sampler view; actual first-frame / presentation; or scanout. A failure at stage 1 is not evidence of a stride violation at stage 5.
3. Select a compatible allocator with a common format/modifier and target device. If the producer needs to meet Grate's exact sampler-derived pitch, require its allocation to actually have that pitch (not a patched descriptor). GBM/device-native allocation when appropriate; if stock Cog's Mesa cannot allocate compatible row pitches, use an explicitly padded/staging buffer with correct copy, or fallback software/shm.
4. If Grate hardware supports arbitrary larger linear pitches for the **specific usage**, its import validator can accept those with width/BO bounds. If sampling hardware derives a fixed pitch, do not relax the sampler gate to accept values its texture descriptor cannot represent. A compositor may convert/copy into an internal compatible resource instead.
5. Handle unsupported modifiers explicitly; do not treat `DRM_FORMAT_MOD_INVALID` or a dmabuf fd as proof of LINEAR. Advertise only importable pairs and reject unsupported combinations before use.
6. Keep separate tests for rendering vs sampling vs scanout and separate importer validation from allocation. Close the gap where import succeeds but later use unexpectedly fails, when caller's bind flags already demand that use.

### Focused width/pitch matrix (32-bpp RGBA/XRGB, byte units)

| Width (px) | Raw row | Align16 | Align32 | Align64 | Diagnostic |
|---:|---:|---:|---:|---:|---|
| 296 | 1184 | 1184 | 1184 | 1216 | Differentiates 32 vs 64 |
| 300 | 1200 | 1200 | 1216 | 1216 | Differentiates 16 vs 32/64 |
| 312 | 1248 | 1248 | 1248 | 1280 | Differentiates 32 vs 64 |
| 320 | 1280 | 1280 | 1280 | 1280 | Control |
| 301 | 1204 | 1216 | 1216 | 1216 | Padding / lower-bound control |

For each width use stride variants below, at, and above expected value while maintaining a valid *actual* allocation; verify GPU readback with distinctive per-row color/pattern, not solely absence of import errors. Check last-row bounds, offset, supported FourCC and modifier, and mismatched BO sizes. Use both sampler and render-target bindings. Add single- and multiprocess tests if synchronisation is in question.

### Suggested Grate importer behavior (design, not patch)

If the usage requires sampling with width-inferred pitch, preflight should reject incompatible imported stride/modifier, but avoid blocking valid *render-target-only* resources if hardware can render them with explicit pitch. For any import:
- Validate handle type, expected plane count, modifier support, format, offset alignment, logical minimum stride, BO bounds with overflow-safe arithmetic, and usage-dependent pitch rule.
- Preserve the declared external stride verbatim once validated.
- Do not infer a trustworthy BO byte size from `stride * height` alone; use actual allocation metadata where available, respecting offset and last-row extent and possible modifier-specific layout.
- Never reinterpret the fd contents by merely rounding its stride.
- Expose error reason (e.g. unsupported modifier, sampler pitch mismatch, insufficient BO extent) to diagnostic logs.

No source edit is recommended until layout semantics are experimentally established and a minimal reproduction exists.

## 6. Evidence limits and release gates

- This review read one public Mesa mirror's current `main` source; it is not a cross-release diff or a statement that older Mesa 25.0.7 import code is identical. The exact local Grate tree is a copied/generated 25.0.7 tree with patch provenance and independent Git identity limitations.
- Neither a live Wayland protocol trace nor a device-rendered row oracle has been run here. Do not claim that the observed SL101 Cog frame problem is caused by pitch, or that a local pitch64 rule is hardware-proven.
- The known working software-rendered Cog recovery remains the default; do not change libEGL/libGBM, browser mode, compositor or device settings during this research.
- Hardware qualification requires exact-hash builds, real buffer metadata, first-frame/RAF/pixel oracle and a reversible test under the SL101 qualification lock.

## 7. Source audit and reproducibility

Public code file links (mirror `chaotic-cx/mesa-mirror`, inspected on 2026-11-03, mutable `main` branch; blob SHAs at inspection):
- etnaviv_resource.c: `166da755f7c459ae4770ccd464c2ba2fb3f62e0f`.
- lima_resource.c: `bb1a314272e08f93efc4bf15a91cf15070c6fdeb`.
- pan_resource.c: `48937053bf3ec0434de97a1757c9f678ac345afc`.
- freedreno_resource.c: `29134ba1337c769618b5b77055d0b1306a7de6d3`.
- nv50_miptree.c: `bcd6e6a5327ca6dd3b04f5014d32041818f4ac9c`.

Local evidence:
- `build/mesa-grate-clean/mesa-25.0.7/src/gallium/frontends/dri/dri2.c`
- `build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate/{grate_resource.c,grate_state.c}`
- `patches/mesa-25.0.7/0033-grate-fix-texture-pitch-alignment-64-byte.patch`
- `docs/upstream/grate-mesa-submission-split-20261103.md`
- `docs/sl101-cog-url-gpu-20261004.md`

**Conclusion:** Fix the producer allocation/layout, or transform buffers at a compatible boundary, not the imported stride metadata. Reject unsupported use at the earliest safe layer. Modifier feedback helps choose *layout families* but does not solve pitch mismatch by itself.
