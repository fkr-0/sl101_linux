# Lane 02: Debian glibc ARMHF Mesa/Grate artifact handoff (2026-11-03)

OCP identity: `SL101-LINUX-02-DEBIAN-MESA-BUILD-20261103-5558AD`. Lane owns only this report and ignored `work/debian-sl101-parity-20261103/02-debian-mesa-build/`. **Status: staged / GPU blocked; not deployment-ready.** No target mutation, graphics tests, or deployment performed.

## Verified read-only baseline

- SSH with strict host-key checking succeeded against the designated Debian target. `uname -r` = `6.18.45`; `dpkg --print-architecture` = `armhf`; `getconf GNU_LIBC_VERSION` = `glibc 2.41`. The target has `/opt/grate-mesa25-clean`, but this is evidence of a local prefix, not source provenance.
- Target Debian packages: `libc6:armhf 2.41-12+deb13u4`, `libdrm2:armhf 2.4.124-2`, `libegl1:armhf 1.7.0-1+b2`, `libgbm1:armhf 25.0.7-2+deb13u1`.
- `readelf -h/-A` on that prefix's `libEGL.so.1.0.0` and `libgallium-25.0.7.so` reports ELF32 ARM, `Tag_CPU_arch: v7`, `Tag_FP_arch: VFPv3-D16`, `Tag_ABI_VFP_args: VFP registers`. These **attributes are not** a complete binary-wide NEON-disassembly check.
- The remote prefix's EGL NEEDED entries include `libgallium-25.0.7.so`, `libgbm.so.1`, `libdrm.so.2`, both Wayland client/server libraries, `libm.so.6`, `libgcc_s.so.1`, `libc.so.6` and `ld-linux-armhf.so.3`. Gallium additionally needs `libdrm_tegra.so.0`, `libz.so.1`, `libstdc++.so.6`. The remote prefix has `libdrm_tegra.so.0.0.0`, but **no regular `libdrm.so.2` was observed under that prefix**; Debian's installed libdrm must be resolved and ABI-checked independently. `/bin/ls` requests `/lib/ld-linux-armhf.so.3`. No host `ldconfig` result was obtained.

## Reusable artifact and exact provenance

- Private, previously qualified glibc overlay archive: `work/sl101-wpe-armhf-build-qualification-20261003/grate-build/grate-glibc-12388168bd458268ea31b9742acac7e27d293dffebaf0dee141cce1a3304a215.tar.gz`; **SHA-256 verified in this lane** = `12388168bd458268ea31b9742acac7e27d293dffebaf0dee141cce1a3304a215` (33,746,680 bytes, inherited recorded size).
- Existing `BUILD-MANIFEST.txt` identifies Mesa 25.0.7, Mesa commit `742a20f48c59e8649533c84c4d49dd95b403f5da`, forked Grate libdrm commit `3e3c53ed85c30331a6c0ba2af349223654caa5dd`, source manifest SHA `e84ff45586e9859f8d2f782caa4138da19a935c66180d1e11c89dbc2ab18846d`, image tag `debian:trixie-slim` (tag alone is **not** an immutable image digest), and compile flags `-march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -DNO_FORMAT_ASM`. Gallium `grate,softpipe`; LLVM disabled per previous qualification. Independently checking source Git trees and builder image digest remains required for a new build.
- Existing `grate-elf-audit.json` reports 18 ARM ELF archive paths, no failures, no flagged advanced SIMD/Q-register/d16-d31 usage. This audit pertains to the **archive**, not automatically to the remote `/opt/grate-mesa25-clean` prefix.
- The tar listing includes EGL, GLESv2, GBM, gallium, DRI and `libdrm_tegra` but **not a core `libdrm.so.2`**. Pair only with a tested exact ABI-compatible Debian libdrm2 (and forked tegra userspace matching kernel UAPI); do not infer provenance from filenames or architecture labels.

## Build / deploy contract

1. Prefer this exact immutable, hash-qualified archive over a redundant Mesa rebuild, **subject to** host-only full-member SHA/ELF/disassembly/NEEDED verification and independently resolved loader/core-libdrm dependencies. A new incremental Docker cross-build must pin the image by digest, source revisions and source-manifest checksum, use the recorded ARMv7/VFPv3-D16 hard-float/no-NEON flags, separate output prefix and manifest, and explicitly include matching forked libdrm. Do not apply unreviewed `grate-upstream-followups` patches.
2. Stage into a versioned private prefix such as `/opt/grate-debian-<artifact-sha-prefix>` through **lane 04 alone**. Never replace `/usr/lib`, stock Mesa/Pixman, loader defaults, or libdrm in place. Require an exact target identity check, archive checksum, dynamic loader `--verify` / `--list` with explicitly selected private dependencies, and no missing symbols before any supervised runtime action.
3. Software mode should remain default and usable: `LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=softpipe`, `MESA_LOADER_DRIVER_OVERRIDE=swrast`. Grate EGL setup, successful link and headless probes cannot establish GR3D pixel correctness. Promotion requires separately authorized live EGL/GBM, exact pixel oracle, browser, input and multi-window validation.
4. Kernel `6.18.45` is **not** the previously visually accepted Nura `7.0.1-postmarketos-grate`. Do not assume Grate DRM ioctl, submit, fence, synchronization or memory behavior is compatible. If UAPI is incompatible, **block hardware acceleration**, preserve Debian software mode, and request an independent kernel candidate packet with exact git commit/config/DTB/initramfs hashes, module and bootloader ABI checks, partition backup and physical recovery plan. No reboot/kexec/boot-default changes under this lane.
5. Rollback for lane 04: stop only its newly started trial clients, remove trial-only environment/launcher bindings, restore saved config files atomically, keep stock Debian libraries untouched and record before/after hashes; do not delete existing Nura or Debian prefixes.

## Evidence classes / outstanding gates

| Class | Result |
|---|---|
| Existing hosted archive | Hash matches; existing 18-object audit accepted as historical evidence |
| Debian remote inventory | Read-only SSH, ELF header/attributes, direct NEEDED entries collected |
| New hosted cross-build | **Not run**: qualified reusable archive exists; no new toolchain or digest pinned |
| Loader resolution and ABI | **Blocked**: exact remote loader mapping and forked/core libdrm compatibility not yet demonstrated |
| Kernel 6.18.45 GR3D UAPI | **Blocked**: not equivalent to Nura 7.0.1 by assumption |
| Live service/browser/GPU pixels/physical input | **Not run**, exclusively delegated to lane 04 and later qualification owners |

## Host-only verification receipt

- `python3 work/debian-sl101-parity-20261103/02-debian-mesa-build/verify_archive.py` — **PASS**: verified archive SHA-256 and resolved all 18 audited tar symlinks/regular ELF members to independently hash-check their actual bytes; `core_libdrm_bundled=False`. The generated machine-readable `artifact-manifest.json` stays private in the ignored lane work directory.
- `python3 -m py_compile work/debian-sl101-parity-20261103/02-debian-mesa-build/verify_archive.py` — **PASS**.
- `make test` — **PASS**, 199 host tests (`Ran 199 tests ... OK`).
- `make check` — **PASS**, `python3 -m compileall -q scripts tests src`.
- `git diff --check -- docs/debian-sl101-parity-20261103/02-debian-mesa-build.md` — **PASS**.

**Evidence boundary:** This manifest verifies archive bytes against the historical audit and does not independently inspect a new builder, execute a loader on target, validate kernel UAPI, or certify GR3D pixels. The omitted core `libdrm.so.2` is an explicit integration dependency rather than a silent success.

Lane 04 should not deploy acceleration from this report alone. First consume the manifest/audit in the ignored lane work directory, confirm loader/core libdrm and kernel UAPI, then conduct bounded, rollback-safe software-first deployment.
