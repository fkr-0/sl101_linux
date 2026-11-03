# SL101 Mesa 25.0.7 Grate — independent GLES2 release gate (2026-11-03)

**OCP task:** SL101-LINUX-20261102-SL101-RELEASE-GATE-QUALIFICATION-20261102-67E56F
**Dispatch attempt:** b3cc8c809a414bfda23b3a504b6f7f04
**Decision:** **NO-GO for unified GLES2 hardware-conformance qualification, accelerated default renderer, and deployment.**
**Scope:** repository/patch/evidence inspection plus non-mutating host qualification and a privately isolated patch dry run. No device operation, renderer switch, shared generated Mesa edit, or source patch edit.

## Evidence boundary / precise identity

- Canonical repository: /home/user/code/sl101_linux; HEAD **fe927c1f1b0a6aae15ae3e5d1f167641dbb4e4a1** (independent state-sync review). Required source audit commit **722b120de35b23d36f356b7833aab08f439ad8bf**.
- The development tree build/mesa-grate-clean/mesa-25.0.7 reports **Mesa 25.0.7** in VERSION, but is **untracked, concurrently edited, and has no own .git directory**. The apparent 'git -C ... rev-parse HEAD' resolves to the enclosing sl101_linux repository and **must not** be reported as a Mesa upstream SHA.
- Local Mesa source archive build/mesa-grate-clean/mesa-25.0.7.tar.xz: SHA256 **592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6**, 46,849,080 bytes. This pins **these archive bytes**, not the origin, vendor Grate source, forked libdrm, or a successfully reconstructed integrated tree.
- Read-only mutable snapshot hashes: grate_screen.c **a15d1e300f7deaf9e610aa8119913952de7ff50142988a80f387f7b278557c0d**; grate_state.c **1d61664691808925be5fdac0cad4a9a5ef3f52ea203bfc13bf21b140ab22c72c**; fp/fpir.h **36e190f6e41c5910168c66a8b7cd6971187cbc0b91e41cd63e8d0852df9b9599**; fp/tgsi.c **946541e9a38878317ab3c04af9997c7b2a6cca828bb78d9f93cbef448f5ac3a8**. These hashes are *not* a coherent frozen build snapshot.
- Repo has unrelated modified and untracked device, browser, Mesa and test artifacts; all preserved. Other workers have path claims. This report owns only its new documentation path.

## Qualification executed in this attempt

| Gate / command | Observed result | Meaning |
|---|---|---|
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/sl101-release-gate-d77215-pycache make test` | **PASS, 190/190** | Python host tests/source contracts and reference oracles only; not Grate execution or hardware |
| Same environment, `make check` | **PASS** | Python syntax only |
| `sha256sum -c patches/mesa-25.0.7/stack-l1.sha256` | **PASS, 12/12** | Original L1 patch **content inventory**; not apply-order or integrated build proof |
| `patch --batch --fuzz=0 --dry-run -p1` for 0010, applied to a **private copy** of the mutable Grate driver source | **FAIL**; grate_state.c hunk 2 at 310 (1/4 state hunks failed) | Current composite cannot serve as a proven strict 0010 replay base; not a test of an accepted pristine Mesa+Grate baseline |
| Complete deterministic strict apply/reverse of all L1 plus mandatory P0 patches | **NOT QUALIFIED** | No approved immutable source+vendor+patch order; LRP/FP conflicts and state overlap open |
| ARM cross build + link against exact matching grate-driver fork libdrm headers/ABI | **NOT RUN / BLOCKED** | No accepted replay tree, host arm-linux-gnueabihf-gcc absent, existing build.sh has unpinned and non-strict paths |
| Actual Mesa GLSL ES 1.00 -> NIR -> TGSI tokens per fixture | **NOT CAPTURED** | glslang legality and Python evidence validator do not exercise actual Mesa lowering |
| Supervised Tegra20 RGBA8, depth/stencil, FBO, fences, GPU fault delta, soak | **NOT RUN** | No device mutation authorised; no independent GPU pixel/timeout evidence |

**Log integrity:** /tmp/sl101-release-gate-67e56f-attempt-b3cc8c8-test.log SHA256 8b2e63881504ea05197d736ff332376a38b49bce24e5c27dbe6270aa64729922; check.log SHA256 622af1168b8fd2fe6434b663ed37566c056090f55feb8570915de6fc72f6f4a6; hashes.log SHA256 936e97fadd65aca74610e3867a3db8b4d4efffe8cef196953aca95213316c366; isolated 0010 dry-run log SHA256 3b1b4b9177077b57c2e3b2682295080d19ccff91f87e071a59c8d59be76ac19d. Temporary logs are local evidence, **not** committed portable build artifacts.

## Unified blockers, not elided by passing host tests

| Category | Release-gate state and observed source/reviewer evidence |
|---|---|
| Fragment uniform ES2 minimum | **P0 FAIL:** fp/fpir.h FP_UNIFORM_COUNT=32 scalar floats = **8 vec4**, while GLES2 requires at least **16 vec4**. The 20261103 FDC010 follow-on verifies only a 32-slot scalar FP_CONST upload method range, with no proven second bank/spill; cannot honestly bump cap. |
| FP/VP complete semantics | **P0 BLOCKED:** independent FP and VP reviews report conflicting FP LRP/RCP/DP patch contexts, register/fetch/indirect issues and incomplete semantics. Patch presence and host numeric oracles are not executable integrated shaders. |
| Discard/control/texture coordinates | **P0 BLOCKED:** patch 0013 emerged during concurrent work but no accepted ALU/PSEQ kill pixel proof; 0015 is a limited controlflow artifact. 0014 handles identity input aliases, not arbitrary computed/projected coords. No actual shader TGSI capture. |
| Texture cube/mip/mirror/format/completeness | **P0 BLOCKED:** 0018 mip/mirror is an isolated artifact, 0024 A8 context was repaired, but 0016 cube not delivered and the driver rejects cube texture targets despite advertising cube levels; unused/incomplete sampler draw behavior unproven. |
| Stencil/blend/depth clear | **P0 BLOCKED:** independent state/sync review documents absent 0020 full ES2 blending, unproven stencil op/ref/write-mask hardware semantics and partial selective-clear support in 0019. P0 stencil follow-on 0032 does not itself demonstrate GPU correctness. |
| Draw/fences and cross-process | **BLOCKED:** 0012 and 0026/0027 have source and reference coverage, but whole-draw preflight/20-bit and 24-bit field overflow, unbounded teardown/BO lifetime and sync faults remain. 0025 atomic preflight absent. Must test actual GPU execution. |
| Mandatory gap patch inventory | **INCOMPLETE:** numbered artifacts 0016, 0017, 0020, 0021, 0022, 0023, 0025, 0028 absent at inspection; 0013 now exists but is not integrated/approved. Number stems 0004 and 0012 are **duplicated** across different L1 patches: sorted glob order is not a deterministic dependency manifest. Respect original worker IDs. |
| Build reproducibility | **P0 FAIL:** current build/mesa-grate-clean/build.sh applies 0006 SFU as special case rather than a strict full L1 stack, fetches fork libdrm master without a commit pin, has `|| true` paths, and emits warnings/manual-apply fallback for 0001/0031. A successful or skipped build here cannot be accepted as fail-closed release proof. |
| Browser and runtime path | **UNKNOWN/FAIL:** clean EGL setup is not validated WPE FDO DMA-BUF initialization, first frame, actual Grate GPU renderer, or pixel/tearing/fence correctness. Independent browser gap notes include unresolved EGL device/DMA-BUF and format negotiation. |
| Physical GLES2 and reliability | **NOT QUALIFIED:** no source-attested GR3D pixel oracle, GPU no-hang soak, GPU fault counters, exact device+binary identity or supervised rollback rehearsal. No GLES2 conformance claim. |

**Independent checkpoints reviewed:** FP stack A5D47B, VP/caps 32D1DE, blend/draw 681E51, shader lanes 947AC6, texture/caps 31D70F, state/sync 6CC4A3, held integration 7BBF52, native IR/pixel 6BB77A and mandatory-gap owners. The integration retry produced hash manifest commit 35a3d22 and A8 repair 38ce0e8; current 190/190 host pass supersedes earlier stale A8 failure **only for host tests**, not for release qualification.

## Deterministic acceptance sequence — blocked at step 1

1. **Exclusive immutable source assembly:** obtain authenticated source Mesa 25.0.7 SHA/tag and SHA256, fork Grate Gallium+EGL/winsys source revision, libdrm fork commit and headers, cross toolchain/sysroot revision. Assemble in a freshly owned isolated tree; no generated Mesa checkout overwrite. Preserve a before/after manifest and treat changes during hashing as invalid.
2. **Explicit strict patch replay:** declare one authoritative total order with each uniquely named patch and SHA256, including all accepted prerequisite and mandatory-gap patches. Use zero fuzz / no unexpected offsets / no already-applied or silently skipped patches; reverse in exact reverse order and reconstruct to confirm. Resolve FP LRP context, 0010 state and 0012 draw/0026/0027 overlaps, and missing 0016/0020/0025 with their owners. The current hash manifest is **not** that order.
3. **Host+native qualification:** run complete `make test` / `make check` and actual built C/Gallium mock tests. Fully cross-compile **and link** Mesa/EGL/Grate and matching fork-libdrm on ARMHF, capture exact ELF ABI/dependencies; fail any missing header/symbol or fallback. Produce real Mesa NIR -> TGSI traces for positive **and negative** ESSL 1.00 shader fixtures.
4. **Source/GPU-truth gate:** verify GLES2 resource floors (16 FS uniform vec4), shader semantics, all mandatory sampler targets/modes, stencil and blend state, FBO pixels, draw preflight, sync/BO safety, and advertised capability truth. If a mandatory semantic is impossible on hardware, retain NO-GO; do not paper over via cap strings.
5. **Supervised SL101 gate:** only after 1–4 and with physical device owner/recovery, run reference-vs-Tegra20 RGBA8 pixel comparison per fixture (record tolerances and raw buffers), fence/timeouts, repeated draw/FBO/map, crash/recovery and GPU hang/fault-delta soak. Record device CID/kernel/modules, binary hashes, logs and complete rollback rehearsal. No unattended deploy/suspend/browser default flip.
6. **Independent approval:** publish exact signed-off evidence, reproduce on a fresh isolate, then reassess GO. This document is expressly **NO-GO**, not a staging approval.

## Preserve and verify software rollback

Boot/current compositor baseline remains **Pixman**; software browser modes may use **softpipe/swrast**. Reference docs/sl101-renderer-switch-20261004.md: trial switch helper accepts only pixman/grate, requires device identity, qualifier lock at /run/lock/sl101-nura-qualification.lock, and is expected to fall back to Pixman on failed Grate startup; detailed logs /var/log/sl101-renderer-switch.log. These are **documented mechanisms**, not a rollback rehearsal by this task. Before any supervised GPU trial, separately verify the known-good installed image, script and library hashes, preserve a recovery shell, rehearse actual Pixman restore and compare pixel readbacks. Do not set a new default or install any new candidate merely to gather evidence.

## Workflow / authority

The exact OCP task currently rejects an ocp_tasks lookup from canonical workspace sl101_linux as **"belongs to a different project"**. This is consistent with the documented prior android-infra migration; do not forge a new ID or replace legacy next.md. The dedicated agent_checkpoint tool may write the exact task ID under the canonical project path; the OCP operator should reconcile historical mapping separately if required. No OCP transition performed here.

**Final decision: NO-GO; next actionable handoff is the existing held integration task 7BBF52 and its original feature-owner tasks, followed by a new independent gate run only after clean pinned stack/ARM/IR and supervised hardware evidence exist.**
