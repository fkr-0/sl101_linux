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
