# NuraBrowser ARMHF ISA audit — follow-up review and corrections

**2026-11-11 follow-up:** physical device .106 runs Cog against the same
WPE WebKit 2.54.0-2 ELF as the NuraBrowser cross-build, with a working
no-SIMD libwebp/libsharpyuv override. The seven findings below were
static suspects and are NOT seven proven reachable SIGILL faults.
No-NEON Cortex-A9 QEMU probes pass for selected libm functions, libgcrypt
SHA-256 and library initialization. See the newer evidence and
remaining hardware/sandbox gates in
wpe254-tegra2-runtime-investigation-20261111.md. The historical strict
audit below remains correctly BLOCKED as a universal ISA guarantee.

Date: 2026-11-10; repository: sl101_linux. Host-only. No SL101 tablet accessed.

## Outcome

The existing ARMHF NuraBrowser ELF remains genuinely linked to
WPE-WebKit 2.54.0-2. The *runtime* release remains blocked pending
Tegra2 VFPv3-D16 compatibility, pinned package closure, plugins and sandbox.

## Review findings and repairs

1. **Disassembler false positive conclusively demonstrated.**
   At libwebp.so.7 .text address 0x1fc0, default objdump -d decoded
   f44fb508 as NEON vst3.8, followed by nonsensical ARM branches and
   undefined instructions. The same address with objdump -M force-thumb
   yields normal Thumb-2 code: push {r3,lr}, mov.w, sub.w and str.w.
   Therefore that *particular* previously cited vst3.8 does not prove
   executed NEON code. Conversely force-thumb can misdecode ARM sections;
   neither single-mode disassembly is a formal ISA-execution proof.
2. **Seven suspect libraries are not automatically seven rebuilds.**
   NEON ELF attributes: libc, JPEG, gcrypt, webp, sharpyuv. Additional
   non-D16 FP attributes: VFPv4 libm and VFPv3 librav1e. libm has
   vfma.f32 and vfma.f64 machine-code representations, unsupported on
   Tegra2 *if actually reached*. CPU-feature/HWCAP dispatch could make
   certain code paths safe; prove reachability before broad rebuilds.
3. **Redundant scanner consolidation.** The old
   packaging/audit-armhf-needed.py now delegates ISA/loader/SONAME
   resolution to scripts/audit-runtime-closure.py, preserving the
   --entry/--output/--libdir invocation. An attribute-only scan no
   longer reports release pass=true. It exposes attributes_clean
   separately and its report schema changes to v2.
4. **Missing PT_INTERP gate added.** The canonical scanner now resolves
   the executable's dynamic loader in addition to DT_NEEDED, audits
   its ABI and ISA, rejects missing/escaping loader symlinks, and limits
   closure graph size to avoid uncontrolled scans.
5. **Expanded low-register NEON heuristics.** Previously e.g.
   vadd.f32 d0,d2,d4 or vabal.u8 d0,d2,d4 could slip past the
   mnemonic/high-register filters. They are now detected without
   rejecting VFPv3 scalar vadd.f32 s0,s1,s2. All suspicious decodes
   remain *heuristic blockers*, not confirmed actual execution.

## Real-artifact results

- ARMHF development image: sl101-nurabrowser-wpe-dev:2.54.0-2
- Binary: work/nura-browser-armhf-20261110/out/build/nurabrowser-core
- DT_NEEDED+PT_INTERP reachable ELF objects: 148
- Missing libraries: 0; ARMHF loader present
- Distinct ISA-attribute suspects: 7; individual findings: 12
- Old compatibility CLI: attributes_clean=false, pass=false, exit 1
- Canonical scanner: status blocked, pass=false, exit 1

This audit does not execute ARM code, verify WebKit sandboxing, observe
the exact runtime HWCAP dispatch, or traverse dlopen/GStreamer/WPEPlatform
modules. It does not authorize deployment. The previous application
ELF-only qualification remains valid but is not a runtime qualification.

## Next gates in order

1. Prove which suspect instructions are actually reachable on Tegra2
   using feature-dispatch analysis and mode-aware ARM/Thumb disassembly.
2. Build a pinned GLIBC ARMHF runtime with only VFPv3-D16-compatible
   executed paths, rebuilding unsafe components as required.
3. Check the full ELF closure including WebKit child processes,
   plugins and dynamic library loading. Establish sandbox proof.
4. Test on real hardware only after separate device authorization.

All changes are host-only, limited to two audit scripts, their unit
tests and this document. Existing unrelated files and QA logs remain
preserved.
