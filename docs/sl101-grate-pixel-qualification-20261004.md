# SL101 Grate strict-ramp pixel qualification — 2026-10-04

## Baseline

The accepted Grate candidate `68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade`
survives the strict full-screen ramp run without a new kernel GPU fault/reset and
without killing the visible desktop. The pixman control is exact. Grate reports
135,476 / 921,600 pixels outside a per-channel tolerance of 2, with maximum
channel error 34.

## Classification

The framebuffer mismatch is not distributed like a pitch, channel-order or
wrong-row failure. Fitting every failing pixel to a convex combination of its
expected texel and one direct neighbor explains essentially all failures at a
small residual. The inferred blend weights cluster at approximately 1/64
increments.

The independently archived compositor-semantics log also shows that wlroots
requests `sampler=0x30000003` for the full-size 1280x720 texture. In the Tegra20
descriptor this enables both linear magnification and linear-within-level
minification. Thus the strict pixman equality oracle is currently conflating two
questions:

1. Is Grate sampling the correct texture, layout, row and channels?
2. Is the linear-filtered GPU result numerically identical to pixman's 1:1 path?

The current evidence strongly favors a small sub-texel phase / interpolation
precision issue exposed by linear filtering, not source-memory corruption.

## Diagnostic rule

Run:

    python work/sl101-grate-ramp-20261004/analyze_ramp.py \
      work/sl101-pixel-cog-20261004/ramp/frame.bgra \
      --output work/sl101-grate-ramp-20261004/baseline-filter-fit.json

Do **not** relax the strict pass threshold from this result. The next bounded
hardware experiment should build the same accepted driver with only the sampler
descriptor forced to nearest as a diagnostic. If the wrong-pixel count
collapses while provenance/fault/desktop gates stay green, the remaining defect
is localized to 1:1 linear-filter coordinate phase/precision. That diagnostic
must not ship: honoring the application's requested filter remains required.

## Remaining decision tree

- Nearest diagnostic nearly exact:
  investigate rasterizer pixel-center / varying interpolation / texture
  coordinate phase while keeping linear filtering semantics.
- Nearest diagnostic still shows the same pattern:
  investigate linker/MFU interpolation and texture-coordinate generation before
  the sampler.
- Large unrelated errors appear:
  reject the experiment and retain the accepted candidate.

The 405-pixel compositor-semantics residual is tracked separately because it has
a materially different topology and includes bounded-damage / edge cases.

## Nearest-filter hardware diagnostic

Using `on_tab.sh`, an otherwise identical diagnostic was built from the accepted
`68a78e18...` blend archive with only `grate_state.c.o` replaced. The replacement
forces the sampler descriptor's minification and magnification filter bits to
nearest while leaving texture format, wrap mode, shader compiler, blend path and
resource code unchanged.

Diagnostic libgallium SHA256:
`ea6a88ddc99f0d5f173d37969a572816fb6432e12124b41005906a237cc630c8`.
It was staged only under the new prefix
`/opt/grate-mesa25-nearestdiag-ea6a88ddc99f0d5f173d37969a572816fb6432e12124b41005906a237cc630c8`.

Results on the live SL101:

| Gate | Accepted linear candidate | Nearest diagnostic |
| --- | ---: | ---: |
| Strict 1280x720 ramp, tolerance 2 | 135476 wrong | **0 wrong** |
| Mixed compositor semantics | 405 wrong | **0 wrong** |
| Strict ramp maximum channel error | 34 | **0** |
| Mixed semantics maximum channel error | 134 | **2** |
| Kernel GPU faults/resets | 0 | **0** |
| Visible desktop survives | yes | **yes** |

The strict-ramp Grate capture is byte-identical to the pixman capture
(`3e93f500d8b3d1870735bfe9d2021ed9f991242efd379676679f978a5404da8f`).
This makes texture memory layout, pitch, channel order, blend correctness and
synchronization poor explanations for the previous 135476-pixel residual.

### Interpretation

The remaining defect is localized to texture-coordinate phase/interpolation as
observed by linear filtering. Nearest filtering is a diagnostic/workaround, not
a general final fix: scaled or transformed surfaces still require the requested
linear semantics. The next driver pass should preserve linear filtering and
correct the coordinate phase/precision path; nearest may only be considered as
a conditional 1:1 optimization if exact no-scale detection is proven.

Archived device summaries live under
`work/sl101-grate-ramp-20261004/device-evidence/`.

## GL_LINEAR-preserving phase pass

A bilinear fit of the accepted Grate strict-ramp framebuffer against the exact
fixture oracle localizes the residual more precisely. Over 8,917 sampled failing
pixels, the best constant subpixel model is approximately **+3/64 texel X and
-2/64 texel Y**. Nearby grid points are measurably worse. This agrees with the
previous observation that inferred adjacent-texel blend weights quantize in
roughly 1/64 increments.

A fuller affine fit shows the phase is not constant. The inferred field is
approximately:

    dx = -0.0320 + 0.08325 * (x / W)
    dy = -0.0371 + 0.00367 * (x / W) + 0.03494 * (y / H)

The X term therefore moves from about -0.032 texel at the left edge to +0.051
at the right edge; Y similarly trends toward zero from top to bottom. Splitting
the fit across plausible quad-triangle diagonals also changes the X slope
materially, so MFU barycentric precision remains a live alternative to a pure
viewport explanation.

The viewport registers use 16x subpixel-space programming. Solving the affine
field for the smallest viewport correction gives an experimental bias/scale
candidate that keeps the requested linear sampler bits untouched:

    X bias  +0.153 register units
    Y bias  -0.285 register units
    X scale +0.666 register units
    Y scale +0.280 register units

Candidate SHA256:
`ee3f169c8e677de79177d056a119461d914f2879138a2dc9791acf3c6e54e79e`.
It is staged at:
`/opt/grate-mesa25-affinephase-ee3f169c8e677de79177d056a119461d914f2879138a2dc9791acf3c6e54e79e`.

The earlier bias-only `+0.75/-0.5` candidate remains staged as a control but is
superseded by this affine candidate for the next hardware gate.

A second diagnostic keeps `GL_LINEAR` but bypasses the MFU perspective reciprocal
and uses affine barycentric coefficients directly. Its SHA256 is
`16d05d89c4ed431c183fb18967e671ee17548031a246e8917eda03d63b99ee0d`.
This is diagnostic only because it is not generally correct for perspective
varyings. Hardware testing rejected it decisively: the fixture failed before
pixel comparison because it never produced two stable nonblank captures. The
visible desktop survived and recent kernel logs showed no matching GPU
fault/reset/timeout. Therefore the perspective reciprocal/barycentric path is
necessary; the fix must refine its precision/phase rather than bypass it.

The Grate TGSI compiler also currently ignores declaration interpolation
qualifiers when installing MFU barycentric setup. An interpolation-aware
candidate now records TGSI interpolation metadata and distinguishes the two
paths: LINEAR/noperspective uses raw affine barycentric coefficients, while
PERSPECTIVE retains the canonical `rcp(r4)` multiplier. Unsupported locations
and mixed LINEAR/PERSPECTIVE varyings in one MFU packet fail closed rather than
silently miscompile.

Both lowering contracts were cross-built for ARMv7 and executed CPU-only on the
SL101 while the GPU qualification lock remained owned by the browser lane:

    PASS tex-perspective: canonical rcp/barycentric/ipl MFU before TEX
    PASS tex-linear: affine barycentric MFU before TEX

This validates the compiler-side distinction without claiming that it explains
the current fullscreen ramp; ordinary GLSL smooth varyings are perspective by
default, so the live GPU gate still decides between viewport phase and MFU
perspective behavior.

### Hardware results after releasing the browser qualification lock

The user authorized closing the active Cog/WPE software review. Its process group
was terminated cleanly and `/run/lock/sl101-nura-qualification.lock` became
free before the GPU tests. No default renderer or persistent service setting was
changed.

The affine viewport candidate
`ee3f169c8e677de79177d056a119461d914f2879138a2dc9791acf3c6e54e79e`
kept `GL_LINEAR` and completed the strict ramp gate, but only changed wrong
pixels from the accepted baseline 135,476 to **133,310 / 921,600**. More
importantly, maximum channel error rose to **201** (baseline 34). Mean channel
error was about 0.369. There were no new kernel faults and visible desktop PID
15243 survived. This candidate is rejected: viewport bias/scale is not the
primary defect and the correction worsens edge/discontinuity behavior.

The MFU perspective-bypass candidate
`16d05d89c4ed431c183fb18967e671ee17548031a246e8917eda03d63b99ee0d`
also preserved the sampler's linear filtering, but failed before comparison:
`fixture did not produce two stable nonblank captures`. The qualification lock
was released afterward, visible desktop PID 15243 remained alive, the desktop
service remained started, and recent kernel logs contained no matching Grate/
GR3D/host1x fault, reset, or timeout. This rejects "remove rcp(r4)" as a fix.

The next source-level target is therefore the **perspective MFU interpolation
precision/phase itself**: reciprocal input convention, barycentric coefficient
precision/packing, or the varying interpolation row path. `NEAREST` remains only
the exact 1:1 control oracle.

Archived evidence:

- `work/sl101-grate-ramp-20261004/device-evidence/affinephase-strict-summary.json`
- `work/sl101-grate-ramp-20261004/device-evidence/mfubypass-strict-result.txt`


### Coordinate-stage separation: sampler vs interpolation

A dedicated ARMv7/GBM probe now separates fragment-varying interpolation from
texture sampling instead of inferring the source from the compositor ramp.

The accepted driver initially rejected a fragment shader that sampled directly
from a uniform texture coordinate (`texture coordinates must come from a
varying input`), so the sampler-only path uses a constant vertex attribute:
all vertices carry the same UV and therefore introduce no coordinate gradient.

A first 2x2 texture exposed format/pitch confounders. The clean discriminator
therefore uses a 4x4 grayscale RGBA texture: each row is exactly 16 bytes and
all color channels are equal, eliminating channel-order ambiguity. With the
accepted driver, row 0 sampled correctly and horizontal `GL_LINEAR` halfway
sampling was exact, but every access requiring a later texture row returned
zero. Nearest centers failed on the same later rows. This identified a separate
sampler-only resource-layout bug rather than a linear-filter bug.

The accepted resource allocator aligned sampler-only rows to 64 bytes even
though the Tegra20 texture descriptor carries no pitch. A diagnostic candidate
keeps sampler-only rows tight (`width * blocksize`) and changes only the
sampler-view validation to match. Candidate SHA256:

`f723ee69ef86717c1b21820aaa4ac051481bac5a0ce8aafd26b906281b440673`

With that diagnostic candidate:

- constant-coordinate `GL_LINEAR`: **9/9 PASS**, including texel centers and
  horizontal/vertical/four-way halfway samples;
- nearest centers: **4/4 PASS**;
- texture-free perspective interpolation: **48/48 sampled points PASS** with
  maximum error **1/255** across both triangle diagonals, 64x64 and 47x31
  viewports, and nonuniform clip-space W sets
  `(0.65,1.35,0.85,1.70)` and `(1.8,0.7,1.4,0.6)`;
- no new kernel GPU fault/reset/timeout and the visible desktop survived.

The same tight-pitch candidate leaves the strict compositor ramp **exactly
unchanged** at **135,476 / 921,600 wrong pixels**, maximum channel error 34.
That proves the raw sampler-only pitch defect is real but orthogonal to the
remaining compositor mismatch.

The current boundary is therefore narrower than either "linear sampling" or
"perspective interpolation" in isolation: both isolated stages pass. The next
target is the **combined interpolated-varying -> TEX handoff**, especially fused
MFU/TEX scheduling, perspective-correct coordinate row preservation, and which
register/row values TEX consumes in the same EXEC. Viewport offset tuning is
closed and should not be resumed.

Evidence:

- `work/sl101-grate-ramp-20261004/coordinate-stage-discriminator.c`
- `work/sl101-grate-ramp-20261004/device-evidence/accepted-coordinate-stage-discriminator.txt`
- `work/sl101-grate-ramp-20261004/device-evidence/tightpitch-coordinate-stage-discriminator.txt`
- `work/sl101-grate-ramp-20261004/device-evidence/tightpitch-strict-summary.json`


### Final discriminator: Tegra20 bilinear weight precision

The combined-path investigation was extended to full-frame tests. Sparse
varying-to-TEX samples can pass while a 1280x720 1:1 ramp exposes the residual:
with `GL_LINEAR`, the direct path produced 19,612 wrong pixels and the
post-texture ALU path 19,629, while the otherwise identical `GL_NEAREST` path
was byte-exact. Texture-free varying interpolation remained correct even when
amplified by 64x, 128x, 256x, 512x and 1024x across the full 1280x720 frame;
each run had zero pixels beyond tolerance and maximum channel error 1/255.
This removes ordinary MFU barycentric precision as the cause.

A constant-coordinate sampler sweep then measured the linear filter directly.
For a black-to-white texel transition, 257 requested fractional positions
(`k/256`, `k=0..256`) produced exactly **65 distinct sample values**. Positions
land on 0/64 through 64/64 filter weights: for example 3/256 snaps to 0/64,
4/256 is exactly 1/64, 7/256 snaps to 1/64, and 8/256 is exactly 2/64. Maximum
error against ideal 8-bit linear interpolation is 3. This is direct hardware
evidence that Tegra20's bilinear filter uses **6-bit fractional weights**.

That explains both the original neighbor-blend classifier and why global
nearest eliminated the residual. It also changes the appropriate fix: do not
alter viewport phase, MFU perspective interpolation, or global sampler
semantics. For a true integer-aligned, untransformed 1:1 blit, ideal bilinear
sampling lands exactly on texel centers and is mathematically identical to
nearest. Selecting nearest only for that exact case avoids Tegra20's finite
bilinear-weight quantization without changing the ideal rendered result.

The wlroots GLES2 candidate therefore selects nearest only when all of these are
true:

- caller requested `WLR_SCALE_FILTER_BILINEAR`;
- texture target is `GL_TEXTURE_2D` (not external);
- texture transform is `WL_OUTPUT_TRANSFORM_NORMAL`;
- source crop X/Y are integer aligned;
- source width and height exactly equal destination width and height.

Fractional crop, scaling in either direction, rotation/flip, external textures,
and explicit nearest remain on their original caller-selected path. The task
local guard matrix covers 12 positive/negative cases and passes all 12.

An ARMv7/musl wlroots build containing only this GLES2 source change was tested
with the accepted Grate driver SHA256
`68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade`.
Because the preserved cross sysroot lacks development packages for optional
DRM/libinput/Xwayland/session features, the headless qualification library uses
test-only zero stubs for those unused optional symbols so stock `labwc` can
load it. Those stubs are **not** part of the production patch.

Strict ramp hardware result with the accepted driver unchanged:

- wrong pixels: **0 / 921,600**;
- maximum channel error: **0**;
- frame SHA256:
  `3e93f500d8b3d1870735bfe9d2021ed9f991242efd379676679f978a5404da8f`;
- no new kernel GPU faults/resets;
- visible desktop survived.

The mixed compositor-semantics capture also has **0 pixels outside tolerance
3**, maximum channel error 2. The remote Python comparator was terminated after
capture while slowly iterating pixels, so the saved hardware frame and oracle
were compared locally with the same qualification comparator. All regions
(background, parent damage, XRGB, XRGB patch, ARGB and overlap) have **0 wrong
pixels**; XRGB/ARGB/overlap reach maximum channel error 2.

Production patch artifact:

- `work/sl101-grate-ramp-20261004/0001-gles2-use-nearest-for-exact-1to1.patch`

Qualification evidence:

- `work/sl101-grate-ramp-20261004/device-evidence/filter-precision.out`
- `work/sl101-grate-ramp-20261004/device-evidence/amplified-interp.out`
- `work/sl101-grate-ramp-20261004/device-evidence/wlroots1to1-strict-summary.json`
- `work/sl101-grate-ramp-20261004/device-evidence/wlroots1to1-semantics-local-compare.json`
- `work/sl101-grate-ramp-20261004/device-evidence/wlroots1to1-semantics-regions.json`
- `work/sl101-grate-ramp-20261004/test_exact_1to1_guard.py`

### Sampler row-pitch production fix

The earlier sampler-only tight-row diagnostic correctly proved that the historical
64-byte row alignment was wrong for small textures, but a production regression
test showed that fully tight rows are also too strict for compositor-sized
textures. The hardware contract is **16-byte implicit row alignment**.

Evidence across resource sizes:

- 2x2 RGBA: 8 row bytes -> 16-byte pitch; historical Stage-C texture probe PASS.
- 4x4 RGBA: 16 row bytes -> 16-byte pitch; GL_LINEAR 9/9 multi-row samples PASS
  and GL_NEAREST lower-row center samples PASS.
- 173-pixel XRGB compositor texture: 692 row bytes -> 704-byte pitch.
- 191-pixel ARGB compositor texture: 764 row bytes -> 768-byte pitch.

The production driver change therefore aligns sampler-only allocations to 16
bytes and accepts a linear sampler view only when `pitch == align(width *
blocksize, 16)`. Render-target, scanout and depth/stencil allocation branches
are unchanged, as is imported-handle pitch preservation.

Qualified ARMv7 driver SHA256:

`fc4f0347fcd3761052255ac1cd610dfecee20187329e9d799358569d14778679`

Hardware regression results with the independently approved exact-1:1 wlroots
filter optimization still present:

- strict ramp: **0 / 921,600 wrong**, maximum channel error 0;
- mixed compositor semantics: **0 / 921,600 wrong at tolerance 3**, maximum
  channel error 2, frame SHA256
  `6e62d628d4983cf9f01f89fa6f7ca30839cf99abd075f010498780932986af6a`;
- no new GPU fault/reset evidence in the pitch-specific probe path;
- visible desktop survived all completed hardware gates.

A deliberately fully-tight diagnostic was rejected because it caused 33,966
mixed-semantics pixels outside tolerance (maximum error 254). This negative
control is what distinguishes the actual 16-byte contract from mere tight
packing.

Evidence lives under
`work/sl101-grate-ramp-20261004/pitch-fix/evidence16/`.
