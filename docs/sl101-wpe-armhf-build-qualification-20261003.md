# SL101 WPE 2.54 armhf host-build qualification — 2026-10-03

## Outcome

Host qualification is **device-ready with one mandatory runtime exclusion**.

The recovered Mesa/Grate build produced a private Debian armhf/glibc overlay
derived from the accepted SL101 Grate driver state. The overlay is not installed
into the host system and is intended only for the isolated Cog/WPE root at
`/opt/sl101-cog-wpe-debian/opt/grate-glibc`.

Hash-qualified overlay:

```text
12388168bd458268ea31b9742acac7e27d293dffebaf0dee141cce1a3304a215
work/sl101-wpe-armhf-build-qualification-20261003/grate-build/grate-glibc-12388168bd458268ea31b9742acac7e27d293dffebaf0dee141cce1a3304a215.tar.gz
```

## Grate provenance

- Mesa: 25.0.7, commit `742a20f48c59e8649533c84c4d49dd95b403f5da`.
- Accepted musl Grate `libgallium-25.0.7.so` provenance:
  `68a78e18af642275d3fec6fc93a4f20cd618d9f951981c7e240d5731e7f29ade`.
- Grate libdrm commit:
  `3e3c53ed85c30331a6c0ba2af349223654caa5dd`.
- Source-manifest digest:
  `e84ff45586e9859f8d2f782caa4138da19a935c66180d1e11c89dbc2ab18846d`.
- Target flags:
  `-march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -DNO_FORMAT_ASM`.
- Gallium drivers: `grate,softpipe`; LLVM disabled.
- Build environment: Debian trixie-slim, armhf cross toolchain.

The deterministic archive includes private EGL/GLES2/GBM, Grate DRI,
softpipe/swrast and the corresponding `libgallium-25.0.7.so`.

## Grate ELF audit

`grate-elf-audit.txt/json` audits all 18 installed ARM ELF objects using
`arm-linux-gnueabihf-readelf` and full disassembly.

Result:

```text
ELF count: 18
Failures: 0
```

All audited objects report ARMv7, VFPv3-D16 and hard-float VFP arguments.
No Advanced SIMD attribute, Q-register use, NEON-only mnemonic or VFP d16-d31
use was found.

This covers the private `grate_dri.so`, `swrast_dri.so`,
`kms_swrast_dri.so`, EGL, GLESv2, GBM, libdrm_tegra and
`libgallium-25.0.7.so`.

## Cog/WPE package set

Audited Debian armhf package versions:

- Cog 0.18.5-1
- WPE WebKit 2.54.0-2
- libwpe 1.16.3-2
- WPEBackend-fdo 1.16.1-1+b1
- GStreamer 1.28.7 package family used by the browser/media path

Core browser objects are clean:

- `/usr/bin/cog`
- Cog Wayland/DRM/headless modules
- `libWPEWebKit-2.0.so.1.11.3`
- `libWPEBackend-fdo-1.0.so.1.10.2`
- `libwpe-1.0.so.1.9.6`

Each reports ARMv7 + VFPv3-D16 and has no audit issue.

### Mandatory exclusion

The merged WPE/GStreamer audit contains exactly one failure among 136 ELF
objects:

```text
usr/lib/arm-linux-gnueabihf/gstreamer1.0/gstreamer-1.0/gst-ptp-helper
FAIL vfp-d16-d31-register
```

Its `__aeabi_ul2d` code uses `d16`, which is outside Tegra20's
VFPv3-D16 register file.

This binary is the GStreamer PTP clock helper, not required for ordinary page
rendering, Wayland presentation, normal browser audio, or the initial software
browse gate. The device deployment must therefore remove/disable this helper
before Cog is launched. The first smoke must fail closed if it still exists.

No claim is made that every future optional codec/plugin is Tegra20-safe merely
because the core browser is clean.

## Cog/WPE tooling state

The recovered Cog/WPE tooling now has:

- manifest-owned CID/kernel verification;
- partial-install cleanup and retry safety;
- package evidence written inside the private root;
- explicit `softpipe` + `swrast` software fallback rather than unconstrained
  llvmpipe selection;
- deterministic rendered-title observation through `wlrctl`;
- live process environment and `/proc/<pid>/maps` provenance capture;
- GPU smoke acceptance requiring the live browser to map the private Grate
  prefix, not merely a separate `eglinfo` process;
- zero new Tegra GPU fault/reset delta as a mandatory gate.

Focused repository test result:

```text
7 passed
```

Shell syntax and Python compilation also pass.

## Serial device handoff

Device apply is allowed only with the exact overlay hash above.

1. Build the Cog bundle with the hash-qualified overlay.
2. Review the dry-run deployment plan.
3. Deploy only into the isolated `/opt/sl101-cog-wpe-debian` root.
4. Remove/disable the incompatible `gst-ptp-helper` before first browser start.
5. Run **software mode first** with explicit softpipe/swrast:
   HTTPS page, observed Wayland title, bounded survival, runtime provenance,
   zero new GPU faults, and clean teardown.
6. Only after software mode is green, run the separate
   Grate + TextureMapper GPU gate.
7. Skia GPU composition remains a later, separate gate.

Firefox/pixman, host Mesa, kernel, boot configuration and PipeWire remain the
rollback path and must not be replaced by this deployment.
