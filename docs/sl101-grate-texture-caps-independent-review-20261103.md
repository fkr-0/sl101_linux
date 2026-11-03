# SL101 Grate texture and GLES2 caps — independent review (2026-11-03)

- OCP: `SL101-LINUX-20261102-SL101-REVIEW-TEXTURE-CAPS-20261102-31D70F`
- Scope: **read-only source/patch review** of 0004 formats, 0011 caps, 0018 mipmap/mirror, 0024 A8; inspection of 0016 cube and 0023 caps readiness. No modification of generated Mesa, SL101 device, or renderer default.
- Verdict: **NO-GO for GLES2 conformance / accelerated browser promotion**. Host checks are green; full stack integration, capabilities, essential texture semantics and GPU pixels are not established.

## Source identity and reproducibility

Review repository HEAD: `c9fd0de5f5410e7a601152352c2ee1f571827da6` (main). Audit baseline: `722b120de35b23d36f356b7833aab08f439ad8bf`. Generated Mesa version: **25.0.7**, under `build/mesa-grate-clean/mesa-25.0.7/`, untracked, dirty and concurrently edited; the hashes below identify the read snapshot rather than a sealed upstream baseline.

| Generated Mesa input | SHA-256 at inspection |
|---|---|
| `src/gallium/drivers/grate/grate_screen.c` | `a15d1e300f7deaf9e610aa8119913952de7ff50142988a80f387f7b278557c0d` |
| `src/gallium/drivers/grate/grate_state.c` | `1d61664691808925be5fdac0cad4a9a5ef3f52ea203bfc13bf21b140ab22c72c` |
| `src/gallium/drivers/grate/grate_resource.c` | `c37e5429811b3e15647a2cdd8a52815082430cce4c7d97723f3e1fa274aec594` |
| `src/gallium/drivers/grate/fp/tgsi.c` | `c2c6d0da7b83e52d885af657797e77556d8b49b66df1563bd7d4ed5a6b4241a8` |

Patch hashes:
- `0004-grate-single-channel-sampler-formats.patch`: `4bdf261028624cf7e3038581292d66c81878064be04c0ea038974e21bdedb8a8`
- `0011-grate-screen-gles2-caps.patch`: `e90e907dad5c01a61c56c2ba7b7ce7018462f74eb2cd4f48fb39f3e50b2972f8`
- `0018-grate-sampler-mipmap-mirror.patch`: `2d1fb03a04da28804e0349e23f417825a6e50be61302d5e1056da93bba5a3ff1`
- `0024-grate-default-a8-sampler-view.patch`: `06dd031cd59f824806679fb9f70949acb75a96798e9042e79c36ac56c4371c47`

The 12-file L1 inventory `patches/mesa-25.0.7/stack-l1.sha256` matches 12/12 at inspection. **It is not a clean-apply order**, a linked build or acceptance. Neither an `0016-grate-cube-texture-sampling.patch` nor an `0023-grate-screen-caps.patch` was present. Do not invent them; cube and capability follow-ups remain with their own owners.

## Feature and control-path findings

| Area | Source/patch evidence | Observed verdict |
|---|---|---|
| Six-face cube | Mesa NIR/TGSI can represent `samplerCube`; inspected `fp/tgsi.c:999-1000` hard-rejects non-`TGSI_TEXTURE_2D`. Screen format gate and sampler-view code accept 2D only, resource mapping has no six-face/level layout. Cube worker doc `docs/sl101-grate-cube-texture-20261102.md` records no verified Tegra20 cube descriptor/implicit-LOD fields. | **Missing/blocked**, not six-face tested; no safe 0016 patch. |
| Mipmap/min filters | `0018` adds POT 2D level offsets, pitch16 rows, level-aware transfer, descriptor MAX_LOD and linear-between-mips bit. `tests/test_sl101_grate_sampler_mipmap_mirror.py` tests **six min filter combinations** in a CPU reference model and compiles/runs a C descriptor probe. | **Host coverage only**; actual Mesa NIR/GL levels, filtering transitions, generated mipmaps and GPU texels unproven. |
| `GL_MIRRORED_REPEAT` | `0018` encodes S/T mirror bits, has a CPU coordinate oracle including negative coordinates. | **Source route + CPU oracle**, not hardware pixels. |
| A8/L8/LA8 | `0004` enables native sampled formats, native swizzle constraints and rejects render/scanout/depth use. `0024` accepts Mesa's default identity A8 view in addition to explicit native swizzle; repair commit `38ce0e8` fixed earlier hunk mismatch. Host 0024 test verifies fuzz=0 replay against its current snapshot. | **Host test green**, but actual GPU A8 channel expansion, bitmap upload, L8/LA8 defaults and filtered samples need pixels. |
| Caps | Snapshot `grate_screen.c:173` advertises `max_texture_cube_levels=16` although cube route rejects it; `:180` sets `essl_feature_level=100` although `FP_UNIFORM_COUNT=32` *scalars*, i.e. **8 fragment vec4 vs GLES2 minimum 16**. `0011` documents the shortfall but still enables ESSL100. | **Confirmed capability-truth/conformance blocker**. Do not fix via an unbacked cap increase. |
| Format/FBO/pitch | `0004` format gate limits A8/L8/LA8 to sample-only; pitch16 is tested in CPU models. `0018` rejects renderable mip chains and unsupported import/mip combinations; no full upload → FBO → readback evidence. | **Incomplete** for GLES2 FBO/render-to-texture and precision/pitch across all dimensions. |
| LOD/invalid samplers | `0018` checks all 16 bound sampler slots; if a sampler exists without an acceptable view or complete chain, it returns false and the draw is suppressed. That is fail-closed against stale descriptors, but not demonstrated equivalent to GLES2's defined incomplete-texture behavior and can reject unused sampler bindings. | **Semantic blocker** independent of successful packer compilation. |

The above source path observations refer to the *inspected* snapshot, not a frozen integrated Mesa application of all patches. Core ES2 cube-map and mirrored-repeat support are mandatory; floating-point textures, fragment derivatives extension and MRT are not core ES2 release gates. A working EGL context, GL shader parser, and a clean host unit test cannot substitute for driver/GPU evidence.

## Exact checks performed this attempt

From `/home/user/code/sl101_linux`:

| Check | Result | Meaning |
|---|---|---|
| `make test` | **PASS: 170 tests, 0 failures/errors** | Repository host tests; contains source assertions, host C probe, software oracles, other lanes. |
| `make check` | **PASS** | `python3 -m compileall -q scripts tests src`. |
| `sha256sum -c patches/mesa-25.0.7/stack-l1.sha256` | **PASS: 12/12** | Input hash inventory only. |
| `git apply --check --directory=work/sl101-grate-mipmap-mirror-0018/before patches/mesa-25.0.7/0018-grate-sampler-mipmap-mirror.patch` | **PASS** | Archived isolated forward applicability; no modification. |
| `git apply --reverse --check --directory=work/sl101-grate-mipmap-mirror-0018/after patches/mesa-25.0.7/0018-grate-sampler-mipmap-mirror.patch` | **PASS** | Archived isolated reverse applicability; no modification. |
| A8 `test_patch_applies_to_snapshot_without_mutation` inside `make test` | **PASS** | Owner's patch test uses disposable tempfile and `patch --fuzz=0` against *current* snapshot. |

Earlier 0018 owner reported 3 ARM source files passing `-fsyntax-only`; **not independently rerun this attempt**. This attempt did **not** produce an integrated clean Mesa patch-stack application, strict ARM compile/link, actual Mesa NIR/TGSI traces, FBO round-trip, EGL/GPU command trace, physical pixel oracle or GPU hang soak.

## Follow-up / release gate

1. **Cube owner**: obtain authoritative Tegra20 texture target/face/implicit-LOD evidence; either implement a separately owned 0016 with six-face and invalid-case oracles, or retain explicit NO-GO. No mapping cube into 2D without sound direction/LOD semantics.
2. **Mipmap owner/integrator**: prove six minification modes, completeness, inactive sampler behavior, NPOT fallback, glGenerateMipmap, level upload, pitch16 and FBO interactions on the *actual* Mesa GL/state-tracker path. Resolve the draw-suppression semantic mismatch. Respect 0018 ownership and review history.
3. **Caps owner**: correct cube/cap advertising only in coordination with actual implementation, fix the fragment uniform minimum through hardware-backed storage or lowering, and avoid treating ESSL100 advertising as proof of conformance.
4. **Integration owner**: freeze a clean Mesa 25.0.7 base with SHA256, replay every independently approved patch once in explicit order (including post-0004 A8 0024), retain failed-hunk evidence, do strict ARM build/link and test negatives. No shared generated build mutation.
5. **Supervised hardware qualification** *after* build gates: test six cube face colors/directions, all six mip filters at LOD boundaries, mirrored UVs (positive/negative), A8/L8/LA8 sampling, pitch edge widths, texture completeness, FBO attach/readback and GPU synchronization against an independent software renderer; capture images, tolerances, logs and rollback. Preserve known-working Pixman/softpipe default.

**Disposition:** independent review completed with critical NO-GO findings. No device mutation, deployment, generated Mesa writes, or false hardware/conformance claims.
