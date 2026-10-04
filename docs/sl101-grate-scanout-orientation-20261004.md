# Grate physical scanout orientation, 2026-10-04

The physical LVDS display was vertically mirrored in Grate while WayVNC and
the raw scanout framebuffer contained upright rows. Left/right and the existing
touch calibration were correct. Restarting Grate recreated the problem.

## Cause and correction

The accepted Mesa Grate resource allocator set the legacy Tegra GEM
`BOTTOM_UP` flag on scanout allocations. The running kernel's
`drivers/gpu/drm/tegra/dc.c` adds `DRM_MODE_REFLECT_Y` for that flag during
atomic scanout, even when the DRM plane rotation property is normal.

A bounded live trial cleared only this flag on the two 1280x800 XRGB scanout
buffers. The user confirmed correct picture and touch. Switching away and back
with the old driver recreated flagged buffers and the inversion.

The persistent Mesa change clears `DRM_TEGRA_GEM_CREATE_BOTTOM_UP` only when
`PIPE_BIND_SCANOUT` is present. Other resource conventions remain unchanged.
The builder replaces only `grate_resource.c.o` in the pinned accepted Grate
archive and relinks Gallium. It does not change touch, output transforms,
kernel, DTB, panel code, or boot selection.

## Installed artifact and live verification

- Accepted baseline library SHA256:
  `68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade`.
- Accepted archive SHA256:
  `6f09746e9c79e218a6287986a2adcd4c0827f5c74d9859171865d1380b5fe240`.
- Corrected library SHA256:
  `32784d505bc5df524d373ef1ab8572c73640099f1b98cdbdd716eaea07289b88`.
- Installed in the root-owned private prefix
  `/usr/local/lib/sl101-grate-32784d505bc5df524d373ef1ab8572c73640099f1b98cdbdd716eaea07289b88`.
- On `sl101-nura`, kernel `7.0.1-postmarketos-grate`, labwc PID 31698 loaded
  the corrected driver. Both new scanout buffers reported `GEM_FLAGS=0`.
- A subsequent Pixman -> Grate round trip produced labwc PID 32361, mapped
  the corrected library, and framebuffer IDs 106 and 103 again reported
  `GEM_FLAGS=0 bottom_up=0` without a live flag workaround.
- Touch configuration SHA256 stayed
  `6a22a74e0eab44d8933f8bd20570558c20c2fc3ba318ac9d746b7e3ec4b1e80d`.
- No new GPU faults appeared in the kernel log. Human confirmation covers
  the live flag trial; the persistent round trip was verified through driver
  mappings and framebuffer flags, pending another physical-screen review.

## Build and qualification limits

Run `python3 scripts/sl101-grate-scanout-build.py --output work/NEW-DIRECTORY`
with the existing accepted archive/source tree, generated Mesa build and
native/cross SDK roots named in the script. Those ignored local inputs are
required; this is not a standalone clean-checkout Mesa build. The script pins
the accepted library, Grate archive and resource source hashes and records
compile/link arguments and output hashes.

The baseline relink control hash was
`3b82e118d331bf093c5681c117bee89dfecdaef491da4a192a6454c3be34ac1c`;
it did not byte-reproduce the accepted shared library. This limits claims of
binary reproducibility. The modified object passed the ARMv7 VFPv3-D16 audit
without NEON, upper floating-point registers or hardware division.

The independent strict headless ramp gate still fails: 135493/921600 pixels
outside tolerance, maximum error 217, with no detected kernel faults.
Comparison with the saved accepted baseline frame changed exactly 17 pixels
in x=583..591, y=274..275; the cause of that small difference is unresolved.
The other pixels match the baseline, whose existing filtering errors remain.
Orientation repair does not qualify overall pixel correctness.

## Deployment and fallback

`scripts/sl101-renderer-controls-deploy.sh HOST LIBRARY` installs the pinned
candidate and updated verifier/launcher. Installation does not restart labwc.
Use `/usr/local/sbin/sl101-renderer-switch grate` for a bounded session restart.
This closes running desktop applications; the switch worker owns the shared
qualification lock and falls back to Pixman if Grate fails its startup check.

`/usr/local/sbin/sl101-renderer-switch pixman` remains the working fallback.
`/etc/sl101-desktop-renderer.conf` still selects Pixman for boot. The previous
accepted driver prefix is retained. Grate is left running for physical review.
