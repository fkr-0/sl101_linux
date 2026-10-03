# Strict Grate pixel qualification and Cog crash diagnosis

Both tests ran on SD CID `035344534c31323880ac79a543010300`, kernel
`7.0.1-postmarketos-grate`, with the visible user desktop on pixman. The candidate
was the visually accepted, isolated Grate binary with SHA256
`68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade`.
No renderer default or desktop service was changed.

| Strict gate | Pixman wrong pixels | Grate wrong pixels | Result |
| --- | --- | --- | --- |
| Coordinate ramp/checker, channel tolerance 2 | 0 / 921600 | 135476 / 921600 | FAIL |
| ARGB/XRGB, padded pitch, blend, overlap, damage; tolerance 3 | 0 / 921600 | 405 / 921600 | FAIL |

Both modes produced two stable captures, mapped the expected driver, generated
no new kernel faults and preserved visible labwc PID 1438/start time. Stability
does not make incorrect pixels acceptable. The mixed-surface global error rate
is small, but its parent-damage, XRGB and overlap regions exceed their individual
0.1% limit. Its background contains 113 wrong pixels with channel error up to
134; treating every discrepancy as harmless filtering precision is unsupported.

An offline nearest-neighbor blend analysis explains 134165 ramp discrepancies
within a 1.5-channel residual; 1311 remain unexplained. Fitted neighbor weights
reach about 0.15625. This suggests texture-coordinate/interpolation/filtering
accuracy as one investigation target, not a demonstrated driver root cause or
permission to relax the oracle. The previously archived precision-aware gate
is distinct from these strict results.

## Repeatable source and evidence

The existing isolated work-directory harness was imported into versioned paths:

- `scripts/sl101-compositor-pixel-qualification.py`: strict per-region oracle,
  isolated pixman/Grate compositors, hash/mapping checks and desktop survival;
- `tests/fixtures/sl101-visual/compositor-client.c`: ARGB/XRGB subsurfaces,
  744-byte padded stride, premultiplied blending and two synchronized commits;
- `scripts/sl101-compositor-pixel-build.sh`: ARMv7/VFPv3-D16 fixture build;
- `tests/test_sl101_compositor_pixels.py`: independent oracle checks, including
  small-region damage that a global average would conceal.

The qualification summary additionally records fixture and script SHA256.
The rebuilt fixture used here has SHA256
`17706fcbac09a807107a8615e844884cc289aae7475a7d83b74ebbfef63375d5`.

Build on the host with the existing cross compiler and copied target Wayland
library, then copy the fixture and Python gate to the tablet:

```sh
bash scripts/sl101-compositor-pixel-build.sh \
  /home/user/code/nuraloumi/target/sl101-cross/bin/armv7-sl101-musl-clang \
  tmp/sl101-nura/visual-regression-20261003/libwayland-client.so.0 \
  /path/to/new/build

python3 /path/to/sl101-compositor-pixel-qualification.py \
  --client /path/to/sl101-compositor-semantics-client \
  --prefix /opt/grate-mesa25-texfuse-68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade \
  --expected-gallium-sha256 68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade \
  --output /path/to/new/evidence
```

The gate takes the device qualification lock and refuses concurrent use. It
never stops the visible compositor. Run the independent host checks with
`python3 -m unittest discover -s tests -p test_sl101_compositor_pixels.py`.

Device evidence: `/var/lib/sl101-pixel-20261004-r1/` and
`/var/lib/sl101-semantics-20261004-r1/`. Host evidence is under
`work/sl101-pixel-cog-20261004/`, including `pixel-evidence.tar` (logs, final
frames and summaries), `ramp/neighbor-analysis.json` and build provenance.
Duplicate intermediate captures remain on the tablet.

Next driver investigations should separate sampling from raster coverage:
compare NEAREST/LINEAR on the same large texture, then isolate the unexpected
background pixels with a minimal subsurface-edge case. Fixes must retain the
strict oracle and pass both gates before a real-display review/soak or promotion.

## Cog: confirmed unsupported instruction in image decoding

The Wikipedia navigation reproduced successfully, followed by a WebProcess
crash. GDB attached to that process stopped the `ImageDecoder` thread on SIGILL
inside Debian's `libwebp.so.7`: `vldr d16`, followed by d17 and NEON `vst1.32`.
Tegra20 has VFPv3-D16 and cannot execute that path. The accessibility-bus warning
is not the demonstrated cause. Debugger evidence is in
`/var/lib/sl101-cog-crash-20261004/` and its host copy in the evidence directory.

A host ARMv7 rebuild of libwebp 1.6.0 disables NEON explicitly and uses
`-O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard`.
`scripts/sl101-webp-no-neon-build.sh` reproduces it in the ARMv7 Debian builder.
The upstream archive SHA256 is checked against Debian's source descriptor:
`e4ab7009bf0629fd11982d4c2aa83964cf244cffba7347ecd39019a9e38c4564`.
See the [Debian source descriptor](https://deb.debian.org/debian/pool/main/libw/libwebp/libwebp_1.6.0-0.1.dsc)
and [upstream configure source](https://chromium.googlesource.com/webm/libwebp/+/refs/tags/v1.6.0/configure.ac).

All six audited ELF paths (two actual libraries plus their symlink aliases)
pass the existing full attribute/disassembly check: ARMv7, VFPv3-D16, hard-float,
no NEON-only instructions, Q registers or VFP d16-d31. Library hashes:

- libwebp: `53f0d406f5614cbeb52ea2373bf8543f5a190e75f7eba883a45836327ff96383`;
- libsharpyuv: `81953a7944d23e8e5f5ded448ff59e6e182fb3a71cce0e915f1e622ca6e0e18d`.

The overlay was staged only inside the private Cog root at
`/opt/sl101-cog-wpe-debian/opt/sl101-webp-no-neon`, and prepended to both launch
modes' library path. The enter helper backup is
`/var/lib/sl101-cog-crash-20261004/enter.before`.

Before live retesting, a concurrent browser qualification worker acquired the
device lock and began its own no-SIMD build. Further browser mutations were
stopped, and exact artifact/backup/evidence paths were handed to that worker
through the project browser-review channel. Browser runtime acceptance remains
pending that owner: prove the repaired library is mapped in WebProcess, repeat
the Wikipedia load beyond the previous crash time, exercise images/JS and verify
that the renderer remains alive with the sandbox enabled. No post-fix browser
success is claimed here.
