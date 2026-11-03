# Banded transformed quad — host-only handoff (2026-11-03)

OCP: `SL101-LINUX-01-BANDED-GEOMETRY-FIX-20261103-1860DB`.
Native packet: `06b1be9e-d9ef-4415-9300-34880c8f7e68`.
Target Nura `.106`, **not** Debian `.100`. No live device access authorized.

## Evidence and provenance

* Producer-reported Cog KMS animation: 262 flips, 2610 GR3D submits / 15 s, ~20 rAF FPS, no render-process crash; these remain **unverified producer observations**. CPU Skia flag enabled, so do not call this native Skia GPU.
* Original evidence (read-only): `fbl/evidence-kms-cog-gpu-example-org-20261103.png` and `fbl/evidence-kms-cog-gpu-banding-anim2-20261103.png`; original HTML pages and `fbl/sl101-fbdump.c` preserved.
* `fbl/09-prompt-grate-banded-geometry.md` reports 256x256 BGRA/pitch1024, attributes `0x0000142d`, stride20, buffer offsets0/12, BO32768. **Recovered read-only source**: `work/scanout-followups-20261103/coordinator-captures/sl101-kms-fmt.log`, 3,693,540 bytes / 12,911 lines, SHA256 `5559b48e43f7f93b3dfa55229d4cd6e3391c9218f12f508b241654ddda98bdb1`. Coordinator reports source as `user@192.168.23.106:/tmp/sl101-kms-fmt.log`; this provenance is a coordinator observation, not independently authenticated running library/build identity.
* **Actual lines 62–64:** `attrib_emit slot=0 buffer_offset=0 elem_offset=0 stride=20`, bytes decode to vertex xy (1024,0), (1024,256), (1280,0). Slot1 `buffer_offset=12` bytes **already begin at +12** and decode UV (0,0), (0,256), (256,0) at *relative offset zero*. The preceding three zero/colour fields in the raw 20-byte interleave explain confusing integer-as-float readings. Each 48-byte hex excerpt gives only three vec2 samples, **not a full four-vertex draw**. Both streams decode consistently; earlier no-decode hypothesis is rejected. Fixture and file SHA tests: `tests/test_sl101_banded_geometry_capture.py`.
* The captured log shows 6288 attrib_emit, 3144 VP-constants and 3144 tex_state lines; two dominant VP constant forms are 16-word (2775) and 4-word (364), with 5 other 16-word texture-height variants. First draw's 16-word constants `[0.0015625,-1,-0.0025,1,0.00390625,0,0,0,0,0.00390625,0,0,0,0,1,0]` combine pixel-to-NDC scale/bias and 1/256 UV scale; these values do not identify draw primitive, indices or raster interpolation. First sample is BGRA `60,40,20,ff` with pitch1024 for 256x256; the same row0/row1 sample does not prove later texels or viewport consistency.
* The recovered debug format **does not log** actual draw primitive, first/count, index data/size, basevertex, per-draw active VBO range, all four vertices, actual compiled VP instructions or installed binary hash. Those are still needed before assigning the bands to vertex fetch, transforms or rasterization.
* Pinned local driver source: `build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate/grate_state.c` SHA256 `575a4a24e1f7738b38b9dd301ac6622da278bc4e42cc8891acfd2faea131aa89`; Git HEAD `11e27edc1240fcd806d6be961360cef3675469bd`. This identifies **host inspection only**, not the binary deployed to .106.
* WebKit 2.54-family upstream (2.53.90): `TextureMapper.cpp::drawUnitRect` supplies `{0,0,1,0,1,1,0,1}` with one `vec2` attribute, stride 0 (effective 8), `glDrawArrays(mode,0,4)`; standard quad uses `GL_TRIANGLE_FAN`. Antialiasing edge path uses a **single vec4** (effective 16) with 12 triangle vertices. `TextureMapperShaderProgram.cpp` uses `attribute vec4 a_vertex`, xy position, zw for edge-control points when enabled; `u_modelViewMatrix` and `u_projectionMatrix` multiply position in column-vector order. Confirm exact *installed* WebKit 2.54 source/binary before identifying this capture as that path.
  - https://fossies.org/linux/www/webkitgtk-2.53.90.tar.xz/webkitgtk-2.53.90/Source/WebCore/platform/graphics/texmap/TextureMapper.cpp
  - https://fossies.org/diffs/webkitgtk/2.52.6_vs_2.54.0/Source/WebCore/platform/graphics/texmap/TextureMapperShaderProgram.cpp-diff.html

## Assessment: no justified driver fix yet

`0x142d >> 8 == 20` according to actual TGR3D header field shift, thus **the encoded 20-byte stride agrees with the observation**. The emitter adds `vb->buffer_offset + e->offset` to its relocation pointer. Its debug sampler starts its hex dump at that already-offset address, so another `+12` when parsing the second stream is a double-count. The two attributes sharing stride20 do not correspond to the normal WebKit TextureMapper static VBO, suggesting a different draw (shader/vertex stage or driver state-tracker translation) was captured. BO total size is **not** the active byte-range length; `start`, `count`, `index_size`, `index_bias`, `basevertex` and primitive matter.

Texture width/pitch alone cannot eliminate bad texcoords, projective w, Y flip, texture sampling, depth/stencil, scissor or raster edge-rule and interpolation defects. Static 30-degree object banding motivates a deterministic-pipeline investigation, not just an attribute stride edit.

Do **not** publish a speculative patch, edit a shared `0038` path or allocate a series number. `patches/grate-banded-geometry/` remains intentionally empty until a frozen base/replay-supported correction exists.

## Host reproducer

`fbl/sl101-banded-geometry-repro.c` makes an isolated EGL pbuffer, compiles GLES2 shaders, draws a rotated square with a column-major 4x4 matrix and reads all RGBA pixels; exit 77 denotes missing host EGL. It accepts `stride offset indexed|arrays` with stride 8/16/20/32 and offsets 0/12 wherever two float32 components fit. Indexed triangles and nonindexed triangle fan use equivalent coverage. Host software baseline (Mesa llvmpipe/softpipe depending installed driver):

    cc -O2 -Wall -Wextra -Werror fbl/sl101-banded-geometry-repro.c -o /tmp/geometry $(pkg-config --cflags --libs egl glesv2) -lm
    EGL_PLATFORM=surfaceless LIBGL_ALWAYS_SOFTWARE=1 /tmp/geometry 20 12 indexed
    python3 -m unittest discover -s tests -p 'test_sl101_banded_geometry*.py' -v

`tests/test_sl101_banded_geometry_capture.py` pins and decodes the source log's first paired attribute dumps; where the captured file exists it validates the complete source SHA and literal fixture. `tests/test_sl101_banded_geometry.py` exercises host byte-decoder (interleaved/packed, strides, offsets, indexed and basevertex) and verifies TGR3D register shift and relocation syntax against current pinned driver source. It also compiles the C reproducer and compares actual GPU-independent software readback hashes across layouts and draw paths. **It does not compile the full Grate emitter**; that remains a hardware candidate gate.

## Exact captures needed for a serial qualification owner

1. Bind recovered `GRATE_DEBUG=format` log and KMS image to exact target `.106`, executable, EGL/GLES build hash, boot/session/time, page URL and compositor/renderer; preserve originals.
2. For each implicated draw capture vertex format/type/components, `glVertexAttribPointer` state, bound array/element BO identities and byte sizes, `vb->buffer_offset`, `e->offset`, stride, pointer relocation, **dump start absolute offset**, raw hex for all referenced vertex bytes, index bytes, draw mode/start/count/index size/basevertex and VP input slots. Sample each VBO at beginning, active start, and relocated pointer without changing the original log.
3. Capture full VP constants/model-view/projection matrices and perspective divide/w, texture coordinate output/varying links, sampler/view state, viewport/scissor/depth/stencil/cull/raster controls and page color texel samples. Distinguish flip source images from live framebuffer.
4. On frozen source/build, replay matched GL API trace first on softpipe, then Grate in a single conductor-owned, rollback-ready live session, compare `glReadPixels` pixels and framebuffer dumps for each stride/offset/draw mode plus static/animated CSS pages.
5. Only if a mismatch uniquely isolates an emitter defect, introduce a minimal patch beneath `patches/grate-banded-geometry/`, record pristine upstream SHA256 and strict `git apply --check`/reverse replay, seek independent native review, and ask packaging owner to allocate a unique series number. No promotion without hardware pixels and teardown/concurrency checks.

No SSH writes, deployment, GPU/KMS run, reboot, renderer/session switch, or default promotion was performed in this task.
