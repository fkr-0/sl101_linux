# SL101 visual regression gate

The Grate default trial was rejected after the user confirmed the same distorted
panels on VNC and the physical screen. GPU submission, fences, surface commits
and a resize soak had not established correct pixels. The desktop is back on
pixman; the direct kernel 7 boot remains installed.

`scripts/sl101-egl-visual-regression.py` now tests a deterministic fullscreen
ARGB8888 wl_shm fixture through isolated pixman and Grate labwc compositors.
It captures raw pixels with input-disabled, loopback-only WayVNC and checks them
against an independent coordinate-ramp/checker/grid oracle. It requires two
identical nonblank captures, an identified renderer, the expected candidate
libgallium hash, no new kernel faults and survival of the visible desktop.
Child processes are cleaned up; no desktop service or boot configuration changes.

Acceptance allows at most 0.1% incorrect pixels with a two-level RGB channel
tolerance. Alpha is ignored because RFB's unused byte is not image content.
A failing CPU control prevents GPU qualification. Exit 0 means acceptance;
exit 1 means a rendering failure or an incomplete qualification.

## Hardware reproduction, October 3

Canonical SD CID: `035344534c31323880ac79a543010300`.
Kernel: `7.0.1-postmarketos-grate`.
Candidate libgallium SHA256:
`541e60b7ef948852be32f9d75c22f5f8aaa8e2e6e3548298aae2f4d0fc2c7815`.

| Renderer | Size | Incorrect pixels | Result |
| --- | --- | --- | --- |
| pixman control | 1280 × 720 | 0 / 921600 | PASS |
| Grate | 1280 × 720 | 919947 / 921600 (99.82%) | FAIL |

Run r3 exited 1 as required. Both captures were stable. No new kernel faults
were detected and the visible compositor PID/start time survived. The Grate
log contains `GL_INVALID_OPERATION in glEGLImageTargetTexture2D(format not supported)`.
This is diagnostic evidence, not a demonstrated explanation of the corruption.

Evidence on tablet: `/tmp/sl101-visual-regression-20261003-r3`.
Host archive: `tmp/sl101-nura/visual-regression-20261003/evidence-r3/`.
Each renderer has process logs, captures, final frame and result JSON;
`summary.json` records the combined gate. This headless reproduction covers
desktop-sized shared-memory composition/readback. It does not qualify touch,
physical scanout, transparency, all buffer formats or the entire EGL port.

## Rebuild and repeat

The host needs Wayland development headers, wayland-scanner, xdg-shell XML and
an ARMv7 musl hard-float cross compiler with its configured sysroot. Copy the
target's `/usr/lib/libwayland-client.so.0` to the build directory. For this host:

```sh
bash scripts/sl101-egl-visual-build.sh \
  /home/user/code/nuraloumi/target/sl101-cross/bin/armv7-sl101-musl-clang \
  tmp/sl101-nura/visual-regression-20261003/libwayland-client.so.0 \
  tmp/sl101-nura/visual-regression-20261003/build
```

Copy the resulting fixture and regression script to the tablet. Run as root
with an unused absolute output directory, retaining the visible pixman session:

```sh
python3 /tmp/sl101-egl-visual-regression.py \
  --client /tmp/sl101-visual-client \
  --prefix /opt/grate-mesa25-qualified-541e60b7ef948852be32f9d75c22f5f8aaa8e2e6e3548298aae2f4d0fc2c7815 \
  --expected-gallium-sha256 541e60b7ef948852be32f9d75c22f5f8aaa8e2e6e3548298aae2f4d0fc2c7815 \
  --output /tmp/sl101-visual-regression-next
```

For a future candidate, supply its reviewed prefix and expected hash explicitly.
Do not turn this known failure into an expected-failure success gate. The driver
fix must make the pixel comparison pass. Local oracle checks run with:

```sh
python3 -m unittest discover -s tests -p test_sl101_egl_visual.py
```
