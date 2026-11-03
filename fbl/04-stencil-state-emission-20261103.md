# FBL04 — reference-matched S8 stencil candidate (2026-11-03)

Canonical OCP continuation: `SL101-LINUX-09-STENCIL-REFERENCE-CANDIDATE-20261103-6DB44C`
Original OCP lineage: `SL101-LINUX-04-PROMPT-STENCIL-STATE-EMISSION-20261103-6C8EF6`
Native packet: `9c6bcee3-8363-4a0f-a866-dfa7a3bc3026` (existing READY packet, NOT a replacement)
Preserved prior commit: `9e34001b61f33fbe0b2c5afe50b3edec83346e6c`

## Sources and provenance

Pinned upstream: `grate-driver/grate` commit `ce8c4d2c62880ee5ffab90fd5f4c0554d4dbcc6d`.
The local cached files were verified by SHA-256 on 2026-11-03:

| Source | SHA-256 |
|---|---|
| `src/libgrate/grate-3d.c` | `d1deb368df39c908babcd1c378b3a3aeeedafe443602420ce05f8e13c9207a31` |
| `tests/grate/stencil.c` | `9a2db9cc0b430c8c05f34a67271f2472655a48cd3f2f8c42a9cb487e1813be71` |

Original source copyright and MIT permission notice remains in the unmodified Mesa driver file; the candidate is an additive patch, not a replacement source tree. The upstream pinned Grate source carries its own preserved copyright and MIT notice.

## Exact reference observation, not hardware qualification

`grate_3d_set_stencil_test` lines 535–571 emits:

1. `HOST1X_OPCODE_INCR(TGR3D_STENCIL_FRONT1, 3)`, followed by `FRONT1` compare-mask/function, `BACK1` compare-mask/function, `STENCIL_PARAMS` test-enable, conditional early-write, and literal `0x8`.
2. `HOST1X_OPCODE_INCR(TGR3D_STENCIL_FRONT2, 2)`, followed by `FRONT2` and `BACK2` reference/fail/zfail/zpass words, each ORed with literal `0x1fe00`.

The executable upstream `tests/grate/stencil.c` includes `CHECK(indices_bo, 0x55)`, `CHECK(indices_bo, 0x11)`, and ZERO/REPLACE cases. These are **upstream reference fixtures**, not measured tablet pixels. In particular, `0x1fe00` is *not* independently proven to be a programmable partial write-mask field.

### Concrete defect corrected from patch 0032

Patch `0032` sent the FRONT2/BACK2 words through `host1x_opcode_imm`, whose immediate field cannot carry the full REF bits at shifts 17–24, and omitted upstream literals `0x8` / `0x1fe00`. The isolated `0038` candidate replaces five immediate emissions with the two source-matched incrementing groups and complete 32-bit data words.

The candidate allows KEEP with any requested mask and ZERO/REPLACE only with `writemask == 0xff`; partial write masks, non-reference stencil operations, invalid stencil comparison enums and S8-incompatible stencil attachments are explicitly rejected. It evaluates both front/back operations and references. Existing `0032` draw gate runs before multi-draw command submission; `0038` extends the creation-time unsupported-state flag.

The Grate reference sets `STENCIL_WRITE_EARLY` only when the fragment shader does **not** discard. This Mesa implementation currently lacks trustworthy per-shader discard metadata for the stencil emitter, so the candidate always leaves early-write **off**. This matches the upstream discard-bearing branch, but not its no-discard early-write optimization; the behavior is intentionally conservative, not claimed cycle-for-cycle equivalent in every branch.

## Host-only tests and scope

- Owner paths: `patches/mesa-25.0.7/0038-grate-stencil-state-fbl04.patch`, `tests/test_sl101_fbl04_stencil_state.py`, this report.
- Private throwaway copy: `/tmp/sl101-fbl04-candidate-a22a/`, created from the current Mesa 25.0.7 source, with `0032` then `0038` applied using `patch --batch --fuzz=0 -p1`.
- `0038` reverse and forward replay verified byte-for-byte. Applying `0038` directly to the current unpatched generated Mesa source fails as expected.
- Compiled C fixture extracts the actual candidate helper/emitter function bodies and uses the real generated `tgr_3d.xml.h` register definitions. It executes full-width FRONT2/BACK2 encoding, full-mask ZERO/REPLACE, compare masks, refs, S8 gating, unsupported/invalid operation and partial-mask rejection, and checks two incrementing dispatch spans.
- `0038` patch SHA-256: `2f1a94791011b148cae01201447a0ba54fdb97b9b5c7fa77b261cf21b924d6e1`.
- Candidate `grate_state.c` SHA-256: `8bfb47466c8e15ec6bf2a3a77d08ced6cb8d9ae9946905df1039da852896a92e`.
- Baseline after `0032` SHA-256: `3057d79e8a81fbe7d68fd6a5f9c93d91923105df724a4dcca0907c07a4606ae6`.
- Installed/generated `grate_state.c` SHA-256: `575a4a24e1f7738b38b9dd301ac6622da278bc4e42cc8891acfd2faea131aa89` (unchanged).

Focused test: `python3 -m unittest discover -s tests -p test_sl101_fbl04_stencil_state.py -v` — **4 passed**.
`make check` — **passed**.
`make test` — **237 tests passed** (host-only, includes existing unrelated tests).

## Limitations and serial qualification gate

This is a reviewable *host-only candidate*, **not** installed Mesa, a GPU test or evidence of correct CSS clipping. It does not implement programmable partial write masks; it explicitly refuses them. Hardware stencil-write, packed depth/stencil, fragment-discard behavior, face winding, later draw interactions, target S8 resource alignment, and compositor pixel output require independent review and one live owner. No target, SSH, KMS, browser, reboot, suspend, build-series, generated source or deployment changes were made.

After independent approval, lane06 must pin the exact series/source baseline for off-device compilation; later GLES2 S8 clear → full-mask REPLACE → EQUAL pixel comparison against softpipe and Cog `border-radius` / `overflow:hidden` pixel comparison require lane01's explicit serial ownership handoff. No accelerated-browser default promotion follows from this host-only candidate.
