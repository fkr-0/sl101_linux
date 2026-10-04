# Production Grate/wlroots pixel stack, 2026-10-04

This combines the qualified 16-byte sampler-only pitch correction, the physical
scanout `BOTTOM_UP` correction, and the exact integer-aligned 1:1 GLES2 filter
optimization. Scaled, fractional-crop, transformed and external textures keep
the requested filtering. The versioned wlroots patch is
`docs/sl101-wlroots-exact-1to1.patch`.

## Artifacts

- Mesa Gallium SHA256:
  `38b7bd1f600d2889a3caeec609e7520842701eab8aa10193f98966ce4e33987c`.
- wlroots 0.20.2 SHA256:
  `0b8c8eb2f1740e8ce258c3d627239a957963e0641cbe6776143afaf14ee56034`.
- Private prefix:
  `/usr/local/lib/sl101-grate-38b7bd1f600d2889a3caeec609e7520842701eab8aa10193f98966ce4e33987c`.

Mesa replaces the resource and state objects in the accepted pinned Grate
archive (SHA256 `6f09746e9c79e218a6287986a2adcd4c0827f5c74d9859171865d1380b5fe240`).
The state object is rebuilt because sampler-view pitch validation is inline in
`grate_texture.h`. The resource allocation clears BOTTOM_UP only for scanout.

wlroots is a complete cross-build, with actual DRM, libinput, session, X11,
Xwayland, GLES2, GBM and libliftoff support. It contains no qualification stubs.
Vulkan and ICC color management are disabled in this private Grate build.
The cross-build uses ARMv7/VFPv3-D16 hard-float flags. The wlroots library and
both replaced Mesa objects passed the instruction audit.
The whole Mesa library does not pass a blanket no-NEON instruction scan: it
inherits the accepted baseline's CPU-dispatched NEON format-unpack routines.
The source returns NULL for these paths when `util_get_cpu_caps()->has_neon`
is false. Both production pixel gates ran successfully on Tegra20; this is
distinct from claiming that the complete Mesa ELF contains no NEON code.

## Local build provenance

Ignored `work/sl101-grate-production-20261004/` holds the isolated development
sysroot, source snapshots, generated Meson configuration, build outputs and
SHA256 manifest. `recipes/sl101-production-mesa.py` records the Mesa object
replacement/relink; `recipes/sl101-production-wlroots.py` records the full
wlroots configure/build. These are local recipes requiring preserved SDK and
accepted archive trees, not a standalone reproducible clean-checkout build.
Alpine development packages were installed only into this isolated build root.
No tablet package upgrade was required.

## Qualification

The exact combined stack passed the isolated strict 1280x720 ramp with zero
wrong pixels, maximum channel error zero, and frame SHA256
`3e93f500d8b3d1870735bfe9d2021ed9f991242efd379676679f978a5404da8f`.
The harness recorded no new kernel faults and survival of visible labwc 32361.
Device evidence: `/var/lib/sl101-production-strict-20261004-r1/`.

The mixed-surface gate also passed: zero wrong pixels in every region at
tolerance 3, maximum channel error 2. Device evidence is
`/var/lib/sl101-production-mixed-20261004-r3/`. Attempts r1 and r2 failed in the
wrapper due to missing arguments, before a complete capture/comparison.
Installed real-display labwc PID 24764 maps both exact production libraries;
WayVNC PID 24921 restarted successfully and its settled capture shows the
upright panel with the Grate badge. Both 1280x800 scanout framebuffers (102 and
106) report `GEM_FLAGS=0 bottom_up=0`. The touch configuration hash remains
`6a22a74e0eab44d8933f8bd20570558c20c2fc3ba318ac9d746b7e3ec4b1e80d`.
No new matching GPU faults appeared in the kernel log. Physical-screen review
of this newly combined stack remains with the user. Local checks pass: 95 unit
tests, syntax/diff checks, and the 12-case exact-1:1 filter guard matrix.
Passing these bounded pixel gates does not establish a
30-minute interaction soak, cold-boot acceptance or GPU browser qualification.

## Installation and fallback

`scripts/sl101-renderer-controls-deploy.sh HOST GALLIUM WLROOTS` installs both
hash-pinned libraries and the matching session verifier/launcher. The private
library path selects both for Grate only; Pixman uses the system libraries.
The existing renderer switch helper starts the review session with automatic
Pixman fallback on startup failure. Previous prefixes are retained and the
persistent boot default stays Pixman.
