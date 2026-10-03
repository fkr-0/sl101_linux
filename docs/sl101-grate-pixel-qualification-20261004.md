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
varyings. If it fixes the ramp while the viewport-phase candidate does not, the
remaining bug is specifically in the `r4` reciprocal/perspective path. If the
viewport candidate wins, the fix belongs in rasterizer pixel-center/viewport
phase instead.

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

### Current live-device gate

Live hardware execution is temporarily blocked by the intentionally exclusive
Cog/WPE software-review process, which holds
`/run/lock/sl101-nura-qualification.lock` until its browser window is closed.
The phase and MFU candidates are staged in distinct `/opt` prefixes but have not
been promoted or substituted for the desktop renderer. Do not bypass that lock.
