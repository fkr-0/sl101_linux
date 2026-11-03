# Tegra20 GR3D linear texture row alignment: source and hardware evidence (2026-11-03)

Canonical OCP identity: `SL101-LINUX-08-TEGRA20-TEXTURE-ALIGNMENT-HARDWARE-20261103-25A82E`.
Repository: `/home/user/code/sl101_linux`. Scope: read-only register/source investigation and a new research note. No GPU source change, no deployment, no live tablet mutation.

## Verdict

**UNPROVEN:** There is no authoritative, publicly documented Tegra20 GR3D linear sampler row-pitch rule establishing 16, 32 or 64 bytes for every format, usage, and mip level. On the inspected local code, a 64-byte gate is an implementation policy; on the inspected upstream Grate source, 32-byte general surface allocation, 64-byte libgrate texture allocation and 16-byte packed mip-level allocation coexist. None alone proves how T20 hardware advances a sampled row.

**Verified source facts:**
- NVIDIA says the Tegra 2 TRM does **not** document internal graphics acceleration hardware. It is not a source for a definitive GR3D descriptor/stride formula.
- The reverse-engineered register database exposes texture pointer `0x710`, texture descriptors `0x720`/`0x721` with format/dimensions/LOD flags, and no explicit sampler row-stride bitfield. Render target `RT_PARAMS` at `0xe10` has an explicit `PITCH` field [24:8]. No explicit field does **not** specify which implicit stride rule the hardware actually implements.
- `grate-driver/mesa` branch `grate` historically rounds ordinary sampler/render/scanout surfaces to 32 bytes and depth/stencil to 256 bytes. `grate-driver/grate` libgrate aligns standalone pixel buffers to 64 bytes through per-format enum metadata, while packing mipmap level rows to 16 bytes.
- The current local Mesa 25.0.7 generated Grate snapshot allocates sampler-only, render-target and scanout rows at 64 bytes and depth/stencil at 256 bytes; sampled views require exactly `align(width*bpp,64)`. An imported DMA-BUF retains its supplied `handle->stride`, so import and sampler compatibility differ.
- The 2026-10-08 Grate/Mesa #19 report concerns **Tegra30 Surface RT** and lists 64-byte pitch among several interacting fixes; it is not T20/SL101 proof.

## 1. Tegra 2 TRM: authoritative scope, not an alignment answer

NVIDIA Tegra 2 TRM landing page: https://developer.nvidia.com/embedded/tegra-2-reference
It explicitly states that internal units such as graphics and video acceleration, controlled by NVIDIA software, are not documented. The publicly described 1,300+ page TRM has no basis for quoting a GR3D texture stride formula. No numbered TRM section establishing a 16/32/64-byte rule was verified; do not invent one. The TRM is gated to registered developers.

## 2. Reverse-engineered registers: envytools, not a hardware specification

Source: https://github.com/digetx/envytools/blob/master/rnndb/tgr_3d.xml (inspected file blob `c69bf9eb8e3779a8f63fc9fda3c0c8032c73635c`).
The requested `AmonTejam/envytools` GitHub repository was not retrievable (404); the inspected maintained public source is `digetx/envytools`.

| Register(s) | XML definition | Relevance |
|---|---|---|
| `0x700`/`0x701` | `FP_UPLOAD_TEX_INST_ID` / `FP_UPLOAD_TEX_INST` | Fragment texture instruction upload, distinct from sampler surface layout |
| `0x710` | `TEXTURE_POINTER[16]` | Sampled surface base pointer/relocation |
| `0x720` | `TEXTURE_DESC1[16]`, format bits 12:8; filters/wrap | Format influences interpretation; no pitch field |
| `0x721` | `TEXTURE_DESC2[16]`, dimensions, log2 dimensions, MAX_LOD bits 15:12, MIPMAP_DISABLE bit 7, NPOT flag bit 6 | Layout dimensions/LOD; no pitch field |
| `0xe00`/`0xe10` | `RT_PTR`, `RT_PARAMS`, PITCH bits 24:8, TILED bit 26 | **Explicit RT pitch**, not a sampler pitch |
| `0x101` | `ATTRIB_MODE.STRIDE` bits 31:8 | Vertex attribute stride; not texture pitch |

Source lines ~276-297 and ~339-345. Headers derived from this reverse-engineered map: https://github.com/grate-driver/grate/blob/master/include/tgr_3d.xml.h and https://github.com/grate-driver/mesa/blob/grate/src/gallium/drivers/grate/tgr_3d.xml.h.

The names `TEX_HEADER` and `TEX_SAMPLER` from the task are not register names in this T20 XML. Actual names are `TEXTURE_DESC1`, `TEXTURE_DESC2`, `TEXTURE_POINTER` and `FP_UPLOAD_TEX_INST`; do not conflate instruction/sampler/RT state. These definitions establish register shapes, **not** the hidden sampler addressing algorithm, base-BO alignment requirement, or cache-fetch behavior.

## 3. Grate Mesa allocator and import history

Source (pinned Grate branch base `5b013b9d5c8affa177d4c1fcb868310852c43982`):
https://github.com/grate-driver/mesa/blob/grate/src/gallium/drivers/grate/grate_resource.c

`grate_screen_resource_create` computes `width0 * util_format_get_blocksize(format)` then rounds to `align(pitch,32)` for any of `PIPE_BIND_RENDER_TARGET`, `PIPE_BIND_SAMPLER_VIEW`, `PIPE_BIND_SCANOUT`, `PIPE_BIND_DEPTH_STENCIL` except depth/stencil uses `align(pitch,256)`. It allocates `pitch * height` bytes and selects `DRM_TEGRA_GEM_CREATE_BOTTOM_UP`. `grate_screen_resource_from_handle` assigns `resource->pitch = handle->stride` after handle import. This source does **not** document why 32 bytes was chosen or prove sampling at arbitrary widths.

The generated Mesa 25.0.7 snapshot is not an independently pinned upstream Git repository and is concurrently mutable:
- `build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate/grate_resource.c:224-265`: render/scanout 64, depth 256, sampler-only 64.
- Same file `:270-318`: FD imports reject nonzero offset; use `drm_tegra_bo_from_dmabuf`; retain `handle->stride`; no modifier/pitch compatibility test in import path.
- `.../grate_state.c:450-499`: sampler-view checks 2D level0 only; `resource->tiled` forbidden and pitch must equal `align(width0 * blocksize,64)`.
- `.../grate_state.c:994-1066`: emits `TEXTURE_POINTER` plus `TEXTURE_DESC1/2`, never an explicit sampler pitch.
- `.../grate_texture.h:101-116`: 64-byte comment and helper are inferred convention, not authoritative hardware documentation.
- `patches/mesa-25.0.7/0033-grate-fix-texture-pitch-alignment-64-byte.patch` asserts 64 from 300px vs 320px RGBA observation. This is a hypothesis because 300*4=1200 bytes, align16=1200 and align32=align64=1216; 320*4=1280 is aligned to all three.

`grate_tex_instr_pack()` in local `grate_texture.h:22-39` only encodes sampler slot (low 4 bits), source/destination register selectors and flags; called by `fp/pack.c::grate_fp_pack_tex`; words uploaded via `grate_program.c` to `FP_UPLOAD_TEX_INST`. No row pitch participates in this instruction encoding. Binding/descriptor policy is a separate path.

## 4. Grate libgrate independent historical evidence

Sources:
- https://github.com/grate-driver/grate/blob/ce8c4d2c62880ee5ffab90fd5f4c0554d4dbcc6d/src/libgrate/grate-texture.c
- https://github.com/grate-driver/grate/blob/ce8c4d2c62880ee5ffab90fd5f4c0554d4dbcc6d/include/host1x.h

`grate_create_texture` lines ~37-80:
`pitch = ALIGN(PIX_BUF_FORMAT_BYTES(format) * width / PIX_BUF_FORMAT_TEXEL_WIDTH(format), PIX_BUF_FORMAT_ALIGNMENT(format))`.

`PIX_BUF_FMT(id,bpp,compressed,align_bytes,tex_w,tex_h)` stores format metadata. In `include/host1x.h` all listed 1x1 formats (A8, L8, S8, LA88, RGB565, RGBA5551, RGBA4444, D16, RGBA8888, BGRA8888, RGBA_FP32) declare `align_bytes=64`, as do listed block-compressed formats (with tex_w=4). This means **libgrate chooses 64 as allocation policy across those formats**, not that 64 is independently proven necessary in all cases. The libgrate creation switch permits only a subset of the enum formats.

Mipmap logic differs: `alloc_mipmap` lines ~407-463 and `setup_lod_pixbuf` ~467-496 calculate each level's size/pitch using `ALIGN(w*bpp,16) * h` and `ALIGN(w*bpp,16)`, respectively; levels are packed sequentially in one BO. The local `0018-grate-sampler-mipmap-mirror.patch` explicitly follows that 16-byte level policy. A blanket 64-byte sampler rule therefore conflicts with this historical mip layout unless the hardware uses a different implicit formula per level/mode, or the earlier implementation is incomplete/incorrect. Neither explanation is verified.

## 5. Nouveau comparison: useful patterns, wrong hardware

Official architecture statement: https://docs.kernel.org/gpu/tegra.html
It distinguishes Tegra20/30/114 built-in GR2D/GR3D through `drm/tegra` from Tegra124+ desktop-derived GPUs through Nouveau. Therefore:
- `nouveau_screen.c` / `nv50_miptree.c` / `nv50_resource.c` describe other hardware. No NV50 pitch number is a Tegra20 requirement.
- Inspected Mesa comparative path `nv50_miptree_from_handle` assigns imported stride to `level[0].pitch` and uses BO tile mode. This illustrates transport of exact imported layout, **not** Tegra20 acceptance.
- Kernel `drivers/gpu/drm/tegra/gr3d.c` governs GR3D device infrastructure, not sampled-texture row decoding. Compare appropriate T20 proprietary traces or reverse-engineered libgrate, not nouveau's pitch math.

## 6. Per-format and mip-level conclusion

No verified T20 hardware evidence establishes a **format-dependent** 16/32/64 formula. There are at least three separate quantities: bytes-per-row (`width * bytes_per_pixel` for uncompressed surfaces), the driver-selected allocation pitch, and the pitch actually inferred/consumed by the sampler. The lack of sampler pitch register and libgrate's format-coded 64 alignment make a common 64-byte policy plausible, but not demonstrated. For block-compressed formats use block geometry (`tex_w`) instead of treating pixels as uncompressed bytes.

Depth/stencil `256` in Grate Mesa is a separate **driver depth surface allocation policy** and must not be applied to A8/RGB565/RGBA sampler import. Render-target `RT_PARAMS.PITCH` can accept an explicit stride that the sampled-texture descriptor does not encode; combined RT+sampler compatibility must be verified independently.

Mipmap level0 and higher levels must be measured separately: the tested local 64-byte level0 gate does not validate the historical 16-byte packed-mip chain. POT/NPOT descriptor modes and filtering may change addressing. Check all supported mips and every row at boundary transitions; host tests of descriptor packing cannot prove pixels.

## 7. Discriminating width-oracle matrix (RGBA8888, four bytes/pixel)

| Width px | Raw row B | Align16 B | Align32 B | Align64 B | What it distinguishes |
|---:|---:|---:|---:|---:|---|
| 296 | 1184 | 1184 | 1184 | 1216 | 64 from 16/32 |
| 299 | 1196 | 1200 | 1216 | 1216 | 16 from 32/64 |
| 300 | 1200 | 1200 | 1216 | 1216 | 16 from 32/64 |
| 312 | 1248 | 1248 | 1248 | 1280 | 64 from 16/32 |
| 320 | 1280 | 1280 | 1280 | 1280 | baseline only |

Suggested format probes: A8 width 32 (32/32/64) and 33 (48/64/64); RGB565 width 144 (288/288/320) and 150 (304/320/320). Widths alone are not proof: hold format/layout/height/descriptor/filter/upload/BO flags constant and explicitly vary allocation pitch.

Executable **hardware** acceptance plan, only under supervised device/renderer-recovery gate:
1. Create linear 2D textures with unique per-row and per-column texels; independently record each BO's offset, exact stride, format, modifier, tiling, resource-bind flags and allocation size. Check memory via CPU mapping without relying on GPU results.
2. For each discriminatory width and format, compare 16/32/64 pitch allocations *with the same width and descriptor*. Reject invalid imports explicitly; record whether allocation, sampler view, draw or presentation fails.
3. Use a pixel oracle (shader nearest sampling and readback of every row/edge; independent softpipe/Pixman reference). Record mismatches by (x,y) and captured descriptor words/relocs. Do not claim pitch from a compositor window merely appearing.
4. Compare native-created and externally allocated DMA-BUF resource, carrying real FD/stride/offset/modifier and verifying the selected allocator. Never rewrite an imported pitch to fake compatibility.
5. Repeat with POT mip chains (level0, level1, last 1x1, each filter mode), NPOT base-level only, and 2D vs render-to-texture separately. Record GPU sync errors and preserve software fallback.
6. Cross-check candidate T20 stride formula against a second device or a minimal controlled GR3D trace before upstream hardcoding; if proven incompatible with external allocations, stage/copy or reject, rather than changing external metadata.

## Verification and limitations

Research snapshot: 2026-11-03. `make test` PASS (199 tests); `make check` PASS (`python3 -m compileall -q scripts tests src`). These are repository **host-only** checks with unrelated concurrent dirty files, not a successful ARM build or a hardware texture verification. No local Mesa source, existing test, deployed graphics state or user-owned dirty file was changed by this task.

The historical reports are hypotheses until isolated on Tegra20. Particularly, Grate Mesa issue #19 https://github.com/grate-driver/mesa/issues/19 is an experimental **Tegra30** multi-fix port, and its author disclaims broader validation. Relevant earlier local notes: `docs/sl101-grate-texsubimage-pitch-alignment-20261103.md`, `docs/upstream/sl101-dmabuf-import-pitch-alignment-20261103.md`, `docs/upstream/grate-mesa-submission-split-20261103.md`, `docs/sl101-grate-texture-caps-independent-review-20261103.md`.

## OCP bookkeeping blocker

The exact supplied OCP task ID does not resolve under the registered `sl101_linux` workspace or the historical `android-infra` workspace: the task service reports **belongs to a different project**. Keep the provided canonical ID and dispatch attempt `51d62571c54948449acbfca99130098c` as-is; do not invent a replacement task, move its authority, or write a legacy next.md. This unique source note is a concrete deliverable independent of that control-plane registry mismatch.
