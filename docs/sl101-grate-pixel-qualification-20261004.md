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
