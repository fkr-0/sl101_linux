# SL101: Cog/WPE 2.54 runtime and Tegra2 no-NEON investigation

Date: 2026-11-11. Scope: read-only physical device inventory and offline
ARMHF cross-host testing. No deployment, device reboot, graphics mutation,
system-library replacement, sandbox bypass or production promotion.

## Corrected architectural conclusion

Cog on real SL101 .106 ALREADY uses Debian WPE WebKit 2.54.0-2. The
NuraBrowser ARMHF ELF is linked to identical WPE WebKit shared-library
bytes. We are changing the embedding API, not moving from an older
WPE engine to 2.54. Cog 0.18.5 uses the maintained legacy
libwpe/WPEBackend-fdo interface; NuraBrowser uses stable WPEPlatform.
The earlier seven-library no-NEON audit is a list of suspects, NOT seven
proven runtime incompatibilities. New WPEPlatform rendering and child
process sandboxing are still separately unqualified.

### Physical Cog private-root facts

Device: 192.168.23.106, kernel
7.0.1-postmarketos-grate-dmavde1-minus-cma.
Private Debian browser root: /opt/sl101-cog-wpe-debian.
CPU Features: half thumb fastmult vfp edsp vfpv3 vfpv3d16 tls (NO neon).

| Package | Installed ARMHF version |
| --- | --- |
| cog | 0.18.5-1 |
| libwpewebkit-2.0-1 | 2.54.0-2 |
| libwpe-1.0-1 | 1.16.3-2 |
| libwpebackend-fdo-1.0-1 | 1.16.1-1+b1 |
| libc6 | 2.43-6 |
| libjpeg62-turbo | 1:3.1.3-4 |
| libgcrypt20 | 1.12.4-2 |
| libwebp7, libsharpyuv0 | 1.6.0-0.1 |
| libwayland-client0 | 1.26.0-1 |

The installed Cog launcher chooses software mode with:

    WEBKIT_SKIA_ENABLE_CPU_RENDERING=1
    WEBKIT_USE_SKIA_FOR_COMPOSITION=0
    LD_LIBRARY_PATH=/opt/sl101-webp-nosimd/lib
    LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=softpipe
    MESA_LOADER_DRIVER_OVERRIDE=swrast

Grate mode appends the private, pinned Grate Mesa directories and retains
the no-SIMD WebP override. Thus this exact WPE 2.54 setup has at least
one previously observed stable about:blank WebProcess run of 61 seconds,
not a complete modern-site, pixel or GPU qualification.

## Cross-builder versus real Cog root, exact SHA256

| ELF object | Bytes identical? | Device SHA256 |
| --- | --- | --- |
| libWPEWebKit-2.0.so.1.11.3 | yes | e198f5d4c9a7abe072545338780a0d99e5e7388c44a03760ce78be72af832c71 |
| libm.so.6 | yes | 93bad2429b538e5c51d271c4140327419c9570921e1b79433276e27f6a99c398 |
| libjpeg.so.62.4.0 | yes | 8a8af48af0173eff599099055e07d2d67ee9bb52fc5bd41b1038262bed631c4c |
| libgcrypt.so.20.8.9 | yes | 679085694a1ee32f9d9939fc855b4e02004015325f5bbd519299a5a301f5bec6 |
| libwebp.so.7.2.0, stock | yes | 32c63970e369fd27934d58fce0c80eeb037297b9e77a453f80763d7face5c09c |
| libsharpyuv.so.0.1.2, stock | yes | e1bbbfff7de5235ebecee65d3773f7d9ce36b17b2630c06b1a090e3970325b3f |
| libc.so.6 | NO | 3c1f1b2519ed30dd35f7ff36aaca0729ca1abfa777f939c853ff0a61a2c5f709 |

The build image instead uses libc6 2.43-7, SHA256
a9caf7a4b40a4f142a375e542b80899724c2cecc8f133c961c3a1265fe6b576c.
Do not upgrade the active Cog glibc merely to make hashes match.

The deployed, WORKING private no-SIMD replacement hashes:

    libwebp.so.7       e1469642b7c28c1ababafcf49ac1874b4f27ce9f4693fbdc76410ef52b2a87e7
    libsharpyuv.so.0  5f55ca48c13c2477dd5e3114a897dcdbafc9c0f2b662ad6b9101e6c8744be295
    libwebpdemux.so.2 d974e63f6e6f4b61c9cd347dd71b5fdc0e4911c861fc976516510e08f3045183

These overrides must be included in the baseline manifest and must load
before the Debian stock WebP/SharpYUV SONAMEs.

## Seven-library ISA triage: observed vs inferred

ARM EABI attributes can summarize optional optimized code that is never
selected. Generic objdump can also misdecode ARM/Thumb interleaving as
NEON; historical inspection confirmed one such false positive at
libwebp .text offset 0x1fc0.

| Suspect | Actual new proof | Workaround / remaining gate |
| --- | --- | --- |
| libc6 | Existing Cog uses glibc 2.43-6. New ARMHF NuraBrowser --help and --remote executed through EXACT Copied Cog 2.43-6 loader+libc under no-NEON QEMU. | Reuse pinned private root; verify all child/loader paths and resolved symbols before promoting. |
| libm | Same exact bytes. QEMU without NEON/VFP-D32 ran sin, cos, tan, exp, log, pow, atan2, hypot, erf, fma, fmaf. Upstream glibc 2.43 dispatches ARM VFPv4 fma with HWCAP IFUNC. | Do targeted math stress and IFUNC verification; do not rebuild solely due optional vfma code. |
| libjpeg-turbo | Same stock bytes; no-NEON dlopen passed. Upstream ARM32 backend probes CPU features, rather than using NEON unconditionally in every build. | Test REAL JPEG decode on device; private -DWITH_SIMD=OFF rebuild only if SIGILL/reachability indicates need. Never force-enable JSIMD_FORCENEON. |
| libgcrypt | Same bytes; no-NEON QEMU initialized 1.12.4 and SHA256("abc") was correct. Upstream CPU HWCAP dispatch. | Test crypto paths; if needed, private-root-only /etc/gcrypt/hwf.deny with arm-neon, then requalify. |
| libwebp | Historical REAL SL101 SIGILL in ImageDecoder recorded vldr d16 and NEON vst1.32; stock lib unsafe on that path. | P0: preserve no-SIMD private overlay. Rebuild option -DWEBP_ENABLE_SIMD=OFF. |
| libsharpyuv | Matching no-SIMD private override exists; stock has NEON attributes. | P0: ship/qualify with matching libwebp and demux overlay; test conversion/encode path. |
| librav1e 0.8.1 | no-NEON QEMU dlopen and version query passed, but encoder NOT exercised. | Test AV1 encode only if needed; otherwise isolate/disable optional encoder path instead of blindly rebuilding. |

Neither dlopen nor one successful SHA256/math operation proves complete
CPU compatibility. Other JPEG/WebP paths, WebKit JS JIT, media plugins,
GStreamer and child WebProcesses still need controlled runtime tests.

## Reproducible offline tests completed

Run from project root:

    sh nura-browser/tests/isa/run_no_neon_qemu.sh

The script checks the immutable local Docker build-image digest and runs
QEMU ARMHF with:

    -cpu cortex-a9,neon=off,vfp-d32=off

Observed guest HWCAP=0x0000e8d7, NEON=0. Eleven libm functions finite,
five libraries loaded with RTLD_NOW, libgcrypt SHA256 known-answer
test passed, rav1e version returned 0.8.1. All without SIGILL.

The actual deployed Cog loader SHA256 is
6c97751a29d861ad32a919edb7e2ad8dcd425ec07278c2890683996c8d9a1702.
It and Cog libc6 2.43-6 were copied READ-ONLY to ignored scratch
work/nura-browser-isa-research-20261111/cog-loader. The new
NuraBrowser ARMHF executable passed --help and entered --remote uri
through those real Cog 2.43-6 binaries under the no-NEON model.
An expected missing private XDG_RUNTIME_DIR ended the remote command;
neither operation initialized a WPE WebView.

An attempted WPEPlatform headless run under ordinary unprivileged Docker
failed because bubblewrap could not create a namespace ("Operation not
permitted"); WebKit aborted after the helper-credentials channel closed.
This is an environment/sandbox gate, not a CPU SIGILL, and must NOT be
marked as a successful browser launch or fixed by disabling the sandbox.

## Lowest-risk remediation sequence

1. **A/B baseline**: stage an isolated copy or mount of the currently
   functional Cog Debian WPE 2.54.0-2 root, loader and glibc2.43-6,
   plus the no-SIMD WebP overlay. Preserve original Cog and host system.
   The new NuraBrowser ABI/initial linker tests are already positive.
2. **Close linker/runtime gaps**: repeat PT_INTERP, DT_NEEDED and
   dlopen/plugin closure over this exact root, with WPEPlatform Wayland
   and WebKit Network/Web/GPU processes. Preserve HWCAP and all hashes.
3. **Headless with mandatory sandbox**: in a correctly provisioned
   namespace, exercise a real WebProcess, local HTML, JS, JPEG/WebP,
   fonts and TLS without touching DRM or the live compositor.
4. **Device-safe headless**: separately authorized, identity-locked,
   one-shot isolated run, strict exit deadline; capture SIGILL,
   SIGSEGV, children, RSS, complete loader mappings, return codes.
5. **Sway Wayland/software**: same Cog WPE runtime, CPU-Skia plus
   TextureMapper, correct authenticated Wayland socket, actual pixels
   and touch/keyboard, compare against Cog after each page fixture.
6. **Optional Grate GPU** only after software qualification, private
   Mesa path and pixel/dmabuf/format/stride checks. KMS/DRM separately
   authorized; never silently switch live rendering defaults.

Important independent boundary: NuraLoumi desktop UID 10000 is not the
Debian browser UID 1000. The new same-UID authenticated browser control
socket is intentionally NOT globally accessible. Provide an explicit
same-UID frontend/broker with exact verbs and credentials, or another
audited bridge. Do not chmod the socket/world or bypass SO_PEERCRED.

Optional future variant: the latest stable upstream WPE release as of
this investigation is 2.54.2 (2026-10-23). It has fixes affecting
WPEBackend-fdo DMA-BUF and memory/crashes. WPE 2.54.1 added compatibility
with libwayland-client >=1.25 at BUILD TIME (missing listener field,
WebKit bug 324760), not proof of a runtime crash with the existing 2.54.0.
Pin a separate 2.54.2 A/B candidate instead of modifying the proven
2.54.0 root and API simultaneously.

## Primary upstream references

- WPE 2.54 overview: https://wpewebkit.org/blog/2026-09-16-wpewebkit-2.54.html
- Legacy vs WPEPlatform: https://wpewebkit.org/blog/2026-10-06-wpe-platform.html
- 2.54.1: https://wpewebkit.org/release/wpewebkit-2.54.1.html
- 2.54.2: https://wpewebkit.org/release/wpewebkit-2.54.2.html
- Wayland header compatibility: https://bugs.webkit.org/show_bug.cgi?id=324760
- WebP SIMD build switch: https://github.com/webmproject/libwebp/blob/main/CMakeLists.txt
- JPEG runtime dispatch: https://github.com/libjpeg-turbo/libjpeg-turbo/blob/main/simd/CMakeLists.txt
- Libgcrypt HWCAP config: https://gnupg.org/documentation/manuals/gcrypt/Hardware-features.html
- glibc 2.43 ARM FMA IFUNC: https://sourceware.org/pipermail/libc-alpha/2025-October/170775.html
- ARM Tegra2 no-NEON: https://documentation-service.arm.com/static/63299276e68c6809a6b41308
- Historical real hardware SIGILL: docs/sl101-wpe-runtime-closure-audit-20261004.md
- Previous false-positive review: nura-browser/docs/armhf-review-retry-20261110.md

## Release rule

Cog works with WPE 2.54, so a blanket claim that WPE 2.54 cannot work
on Tegra2 is disproved. This does not qualify the DIFFERENT WPEPlatform
embedding path, new browser UI, sandbox, accelerated frames or all
decoders. Those remain evidence gates, not arbitrary seven-library
rebuild prerequisites.
