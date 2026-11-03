# Lane 04 — Tegra20 S8 stencil-state emission (2026-11-03)

Canonical OCP task: SL101-LINUX-04-PROMPT-STENCIL-STATE-EMISSION-20261103-6C8EF6
Native packet: 9c6bcee3-8363-4a0f-a866-dfa7a3bc3026
State: **blocked on verified stencil write-mask semantics and supervised pixel qualification**.

## Verified host findings

- Read `AGENTS.md`, `README.md`, `docs/MIGRATION-20261003.md`, `docs/sl101-grate-blend-stencil-20261103.md`, patch 0032 and the local `tgr_3d.xml.h`.
- XML: stencil ZERO=0, KEEP=1, REPLACE=2, INCR=3, DECR=4, INVERT=5, INCR_WRAP=6, DECR_WRAP=7.
- XML: `STENCIL_PARAMS` test-enable bit 0x20; early-write bit 0x40. `STENCIL_FRONT2` REF mask 0x03fe0000 shift 17; FAIL bits 0..2, ZFAIL bits 3..5, ZPASS bits 6..8.
- Patch 0032 emits front/back compare, masks, runtime references and KEEP-only operations, with S8-gated test enable. It explicitly rejects writes before submission; it does not establish actual CSS stencil clipping.
- The XML does **not** define the stencil write-mask field or prove behavior of candidate reserved bits. Adjacent unused bit positions are not authoritative evidence of a write mask. Enabling REPLACE without that proof would be unsafe.
- Prior device report says EGL S8 config is selected and GPU submits occur. It does **not** prove stencil pixels, compositor scanout or rounded-corner clipping.
- No live device access, shared Mesa build-tree editing, patch-series change, or browser restart in this lane.

## Implementation decision

No speculative mutating-stencil patch is introduced. Existing patch 0032 remains the safe fail-closed candidate until the write-mask/register semantics are established by independent source or supervised isolated device experiments. Writing fake REPLACE state could incorrectly claim clipping support or corrupt output.

## Qualification gates

1. Obtain authoritative register decode for stencil write mask and full front/back reference, mask, compare and operation semantics.
2. Produce a lane-owned `0038` patch against isolated, reproducible Mesa source; preserve existing 0032 functionality and reject unsupported configurations.
3. On lane01's **durable explicit ownership handoff**, run GLES2 S8 clear → KEEP/REPLACE mask → EQUAL quad → glReadPixels, compare pixel-by-pixel with softpipe, including mask variants.
4. Validate Cog rounded border-radius plus overflow:hidden against software pixels. Independently review, then hand candidate to lane06 for series/build/deploy integration.
5. No accelerated browser default promotion until real pixel and stability evidence.

## Checks

`tests/test_sl101_fbl04_stencil_state.py` validates the known opcode constants, field allocations and fail-closed contract from repository sources. It is a host source-level test, **not** a hardware test.
