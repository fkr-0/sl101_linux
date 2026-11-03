# SL101 Mesa 25.0.7 — independent state synchronization review (2026-11-03)

- OCP task (unchanged): `SL101-LINUX-20261102-SL101-REVIEW-STATE-SYNC-20261102-6CC4A3`
- Dispatch attempt: `930fc58d5f984e7183fbc7871cb1f9f5`
- Repository: `/home/user/code/sl101_linux`, Git HEAD **`661bbb15e27ea9251fcb038c843963380ef7e286`**, dirty and untracked artifacts preserved.
- Required canonical docs consulted: `AGENTS.md`, `README.md`, `docs/MIGRATION-20261003.md`, `docs/sl101-gles2-required-feature-audit-20261102.md`, and relevant original worker/reviewer checkpoints.
- No device command, renderer switch, shared Mesa modification, patch overwrite, or legacy `next.md`.
- **Verdict: NO-GO for GPU hardware safety, full GLES2 state correctness and renderer promotion.** Source inspection and CPU oracle results are not pixel evidence.

## Exact provenance and replay boundary

| Artifact | SHA256 |
|---|---|
| `0010-grate-blend-expansion.patch` | `43eabcde3d1b141077b1914ca6b0cc4c7872794e7264c315347db2f960804694` |
| `0012-grate-draw-path.patch` | `ea9831d9aa0f1a69a688a216c7c7850ce8facf044a4b13a647efcdc1503ab4d0` |
| `0019-grate-selective-depth-stencil-clear.patch` | `26790af2ea70b900ad2704e75965d4fc7d09c9300884752736f697bf6d934256` |
| `0026-grate-draw-restart-multidraw.patch` | `5671e5a056cd06a4d80c38708edaa91247b515b345cc52a62033c1ad8c46c570` |
| `0027-grate-fence-error-lifetime.patch` | `b6603c742eab64efbca86a97b2a2d3590c9c4b43de8e1e550f5ca12968a7178d` |

`0020` (full blending) and `0025` (draw atomic preflight) **do not exist** at the requested `patches/mesa-25.0.7/` locations. Separate active/blocked worker outputs are not a substitute. Current untracked driver snapshot is a mutable composite, **not an immutable pristine Mesa base**.

Source SHA256s copied (read-only) from `build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate`:

- `grate_resource.c` `c37e5429811b3e15647a2cdd8a52815082430cce4c7d97723f3e1fa274aec594`
- `grate_draw.c` `9822c85b66df9adde20b0bff0db751f6fd488a22ff2ed431b9107dc3dd46da12`
- `grate_context.c` `9e77211921e3e1d2d04015d67a924c8cf4771dca4912dfc7164683d7d54bed4a`

Private source copies only: `/tmp/sl101-6cc4a3-replay-nTW7hH/` (includes ephemeral rejected hunks; not accepted source). Using `patch --batch --fuzz=0 -p1`:

1. `0019` against copy of current `grate_resource.c`: **PASS**.
2. `0026` against current `grate_draw.c` copy without 0012: **FAIL 2/2 hunks** (94, 468).
3. `0027` against current `grate_context.c` copy without 0012: **FAIL 2/2 hunks** (309, 348).
4. New separate copy of current driver subtree, trying ordered `0010` then `0012` etc: **STOP at 0010**; `grate_state.c` hunk 310 fails even with `--fuzz=0`; partial temp output discarded from qualification. Do not say stack replay passed.

This proves the *current moving composite* is not an admitted replay base. It does **not** disprove that the patches could replay on an exact immutable Mesa source with all preceding owner patches applied in the correct order. That clean replay, full ARM build/link and real device qualification remain blocked.

## Independent executable reference matrix

`tests/test_sl101_state_sync_independent.py` is an **oracle**, not a driver test. Seven host-only tests cover:

- RGB and alpha blend with separate equation/factor selection; `ADD`, `SUBTRACT`, `REVERSE_SUBTRACT`, the core ES2 factors, constant blend color, and per-channel color-write masks. Float comparisons are tolerance-normalized in the explicit fixed example.
- Published four 0010 modes as examples: replace, standard alpha, premultiplied source-over and additive; notably standard-alpha *output alpha* equals `src.a*src.a + dst.a*(1-src.a)` for the 0010 all-channels-SRC_ALPHA variant.
- Front/back-independent stencil compare/reference/read masks; `NEVER/LESS/LEQUAL/GREATER/GEQUAL/EQUAL/NOTEQUAL/ALWAYS`, fail/depth-fail/depth-pass branches, all eight ES2 stencil ops, saturated versus wrapping increments/decrements, byte write masks and preservation of unmasked bits.
- Selective depth/stencil clear preservation reference for four flag combinations. This models a *future hypothetical packed surface*, not hardware support for one in 0019.
- Strict reject-before-any-submission model for connected non-indexed count **65537**, source vertex IDs above 65535, 20-bit byte OFFSET, 24-bit FIRST, out-of-range u32 source indices, and zero-count no-op.
- Source-contract assertions explicitly identifying 0026 restart/zero-count guards and 0027's remaining fault-safe teardown limitation.

**Observed new focused oracle**: `PYTHONPYCACHEPREFIX=/tmp/sl101-state-sync-review-pycache PYTHONPATH=src python3 -m unittest discover -s tests -p test_sl101_state_sync_independent.py -v` → **7/7 PASS**. These are mathematical expected results, not actual Grate raster/Gallium backend execution.

## Findings and gates

| Severity | Scope | Grounded result | Required resolution |
|---|---|---|---|
| P0 | Stencil | 0019 gates Z16-only depth and S8-only stencil clears; no verified combined attachment, front/back compare/ref/test/op/write-mask emission. The register header alone does not establish write-mask semantics. | Authoritative Tegra20 register semantics plus real state-matrix pixels for both faces, scissor, depth pass/fail and all operations. Do not invent bits. |
| P0 | Blend | 0010 recognizes only replace, premultiplied OVER, standard SRC_ALPHA/INV_SRC_ALPHA and additive; other core ES2 factors/equations and color masks are rejected. 0020 absent. | Implement and review full factor/equation/RGB-alpha/color-mask paths in separate 0020; compare independent oracle to GPU pixels. |
| P1 | Draw | 0012 may submit some connected line-loop chunks before it encounters a nonrepresentable vertex at 65537. It can silently mask 20-bit OFFSET and 24-bit FIRST. No 0025 whole-multidraw preflight artifact. | Reject entire invalid operation before first submission, including all later multidraw entries and split suffixes; test exact boundaries. |
| P1 | Draw | 0026 adds explicit restart rejection, per-entry u8/u16 bounds and zero-count u32 continue, but does not itself guarantee whole multidraw atomicity; replay on admitted 0012 base unverified. | Mock 0-count and restart, 2046/2047/2048/65535/65536/65537, overflow and high indices; actual C compile and stream counting. |
| P1 | Fences | 0027 bounds per-channel/exported waits and preserves failing exported references for CPU-map retry; on destroy it releases userspace refs after failure, but kernel BO pinning unproven. `grate_channel_delete` still has an unbounded last-fence wait in the inspected snapshot. | Verify ABI/kernel job-BO lifetime, compile a fault-injection C mock, ensure bounded teardown, preserve observable error and no map on failure. |
| P1 | Integration | Current mixed Mesa snapshot fails deterministic 0010/0012/0026/0027 stack replay. Owner patches untracked/missing and other lanes may mutate source. | Pin immutable source tarball/commit plus complete ordered patch manifest with hashes, zero-fuzz clean apply and reverse, strict ARM C compile/link. |
| Release blocker | GPU | No supervised GR3D pixel comparison, real stencil register trace, GPU timeout/fault delta, BO lifetime proof or rollback rehearsal in this review. | Maintain Pixman/softpipe recovery; hardware **NO-GO** until owner-supervised pixel/timeout/rollback evidence and independent signoff. |

### Source-specific qualifications

- The 0019 safety guard prevents incorrect full fills of a *disjoint* Z16/S8 surface but says nothing about preserving both components of a future packed format. Unsupported format returns without a clear, not a conformance implementation.
- 0026 preflight is **per draw** after loop entry, so a later invalid multidraw can still fail after earlier GPU jobs; checked u32 conversion and unaligned memcpy are useful but not whole-operation atomicity.
- 0027 `timeout_ms=5000` applies sequentially to each wait; worst-case elapsed time is not a single 5-second bound. Dropping references on destruction after failure must not be interpreted as completed GPU work.
- `make test` does not run an ARM or live-GPU test, and the independent oracle cannot establish FP20/fixed10 blend register lifetime, physical stencil masks, kernel pinning or readback ordering.

## Host verification and continuation

- Baseline, before adding this review's 7 oracles: `make test` → **170 passed**, `PYTHONPYCACHEPREFIX=/tmp/sl101-state-sync-review-pycache make check` → **PASS**. Older A8 sampler patch-context failure is no longer present in the current tests.
- Focused oracle → **7/7 passed**; complete post-addition `PYTHONPYCACHEPREFIX=/tmp/sl101-state-sync-review-pycache make test` → **177/177 PASS** (exit 0); post-addition `PYTHONPYCACHEPREFIX=/tmp/sl101-state-sync-review-pycache make check` → **PASS** (exit 0).
- All original worker tasks/checkpoints remain separate. No edits to stencil 0019, blend 0010, draw 0012/0026, fence 0027 or other code were made.

Next task: once 0020 and 0025 actually exist and owner claims are released, choose a **fresh privately owned immutable Mesa 25.0.7 source snapshot**, prove source hash, replay **all prerequisite patches** including 0010+0012 exactly once with zero fuzz, then 0019/0020/0025/0026/0027 in a documented order. Compare host C mock state/stream/fence behavior to oracle, ARM compile/link, and only with supervised SL101 access run hardware stencil/blend/draw/fence tests with explicit abort and rollback. On any failure retain NO-GO.
