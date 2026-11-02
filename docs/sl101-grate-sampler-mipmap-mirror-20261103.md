# SL101 Grate GLES2 2D sampler mip/mirror — isolated patch 0018 (2026-11-03)

## Authority and exact source

- OCP: `SL101-LINUX-20261102-SL101-SAMPLER-MIPMAP-MIRROR-20261102-B6AB58`.
- SL101 repository HEAD during inspection: `722b120de35b23d36f356b7833aab08f439ad8bf`.
- **Generated/untracked Mesa 25.0.7 driver snapshot**, not tracked by HEAD: `build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate/`; only read/copied into ignored `work/sl101-grate-mipmap-mirror-0018/before/`, never edited in place.
- Pinned Tegra20 register and layout reference: [grate-driver/grate at ce8c4d2](https://github.com/grate-driver/grate/tree/ce8c4d2c62880ee5ffab90fd5f4c0554d4dbcc6d), `src/libgrate/grate-3d.c` and `src/libgrate/grate-texture.c`. Its packed descriptor uses bit 3/2 for S/T mirrored-repeat, bit 27 for minfilter mip-level interpolation, bit 7 in DESC2 for mip-disable, bits 12..15 for MAX_LOD. Its software mip chain uses concatenated levels, row pitch aligned to 16 bytes.
- Independent worker 10 original texture-format patch `0004-grate-single-channel-sampler-formats.patch` and later A8 work have separate ownership and integration. This patch assumes the checked *generated* Mesa snapshot and must be replay-checked against the ultimately admitted patch stack.

### Snapshot SHA-256 (`before/src/gallium/drivers/grate/`)

| Input | SHA-256 |
|---|---|
| `grate_draw.c` | `94e281eed5f935ed17c8b4949e94d8b297e0cb5e4df5a5006fbe505cbdd4f474` |
| `grate_resource.c` | `c37e5429811b3e15647a2cdd8a52815082430cce4c7d97723f3e1fa274aec594` |
| `grate_resource.h` | `37925080f0fb378f8414e02970078f2bffa5f09ef62f6e142feb7a3cfb9722a0` |
| `grate_state.c` | `0c2f311c978d580a12b1d87f5ce7f71cbcf9ef412ed2ed28da8d199cbddc680a` |
| `grate_state.h` | `0a3fd71ef1cb8c469b2b4ed7adc4a097881cb798e9453c45c56b4fb23dc781ee` |
| `grate_texture.h` | `1e82b76cfe2671f39c1aa5b9009a484be9939a9d59e2fd6e4198f9118dfc08e6` |

## Patch behavior and strict boundaries

`patches/mesa-25.0.7/0018-grate-sampler-mipmap-mirror.patch` modifies six Mesa Grate driver files **only**:

- `grate_texture.h`: extended desc1 for `MIRRORED_REPEAT` S/T and between-mip linear; desc2 encodes valid POT mip MAX_LOD and mipmap enable/disable while preserving original level-0 wrappers.
- `grate_resource.h/.c`: mip-level offsets and pitch16 in one BO, level-specific CPU map/transfer pitch and offset, bounds checks, fail-closed rejection of NPOT mip chains and unsupported imports/render-target mip chains. Legacy level-0 allocation survives.
- `grate_state.h/.c`: accepts Gallium mirrored repeat and three min-mip filtering modes, accepts multi-level views, generates descriptor registers, rejects unsupported/short/incomplete mip bindings rather than using stale texture descriptors; missing source view-validation return is repaired.
- `grate_draw.c`: checks mapped 2D sampler/mip pairs before emitting commands, aborting invalid draws.

**Explicitly excluded:** cube targets/six-face orientation (separate 50768 worker), computed TEX coordinate changes, A8 default-view work, stencil/blend, default renderer switch, device mutation, or new GLES2 claims.

## Reproduction / no shared tree edits

Commands from repository root (ignored scratch `work/` is deliberately retained for rollback and provenance):

```sh
# Replay patch against the archived copy of the exact generated Mesa inputs.
git apply --check --directory=work/sl101-grate-mipmap-mirror-0018/before \
  patches/mesa-25.0.7/0018-grate-sampler-mipmap-mirror.patch

# CPU oracle and actual C header register-packer compilation.
PYTHONPATH=src python3 -m unittest discover -s tests \
  -p 'test_sl101_grate_sampler_mipmap_mirror.py' -v

# Cross ARM syntax-only against Meson compilation commands using the Grate fork
# libdrm header; Docker has a read-only mount and no network/device access.
docker run --rm --network none --read-only --tmpfs /tmp \
  -v /home/user/code/sl101_linux:/src:ro \
  mesa-grate-build:latest \
  python3 /src/work/sl101-grate-mipmap-mirror-0018/check_cross.py

make test
make check
```

## Verified host evidence (no GPU pixel evidence)

- Isolated `git apply --check`: PASS; read-only `git apply --check --directory=build/mesa-grate-clean/mesa-25.0.7` on the current generated Mesa snapshot: PASS. Neither applied the patch to the shared tree.
- Isolated `git apply` and `git apply -R --check`: PASS; patched files replay bit-for-bit against the after snapshot (the latter also contains additional unchanged headers for compilation).
- Six local Python/host tests: PASS, including actual `cc -std=c11 -Wall -Wextra -Werror` descriptor packing. Tests cover independent CPU LOD/reference layout and mirrored coordinate examples; **not** a Mesa TGSI execution or hardware texel test.
- ARM `-fsyntax-only` on isolated `grate_resource.c`, `grate_state.c`, `grate_draw.c` with matching grate-libdrm header and recorded compile commands in read-only/offline Docker: all 3 PASS. This is neither full build/link nor device acceptance.
- `make check`: PASS.
- `make test`: FAIL, 160/161 passed at last run. Unrelated existing test `test_sl101_grate_default_sampler_view.DefaultA8ViewTests.test_patch_applies_to_snapshot_without_mutation` fails patch hunk `grate_state.c:407` from separately owned A8 patch `0024`, not from patch `0018`. Must be reconciled with A8 owner; do not modify their test or patch here.

## Remaining blockers / acceptance gates

1. **Not fully GLES2-conformant.** Incomplete mip/NPOT sampler fallback currently rejects draw to avoid corrupt/stale hardware, whereas GLES2 incomplete textures have defined observable semantics; must coordinate state-tracker fallback and actual emitted TGSI texture units rather than gate unreferenced sampler slots. No capability promotion.
2. Hardware-matched descriptor fields and BO packing are established **from original reference source**, not device-observed texels. Needs supervised Tegra20 readback vs software reference for all six minification modes, lod transitions, 1x1 and non-square POT chains, U/V mirrored and negative coords, filter seam boundaries, glGenerateMipmap, and negative/unsupported combinations.
3. No clean linked ARM build, no Mesa NIR→TGSI traces, no end-to-end FBO or GPU fence evidence. Independent patch integration must ensure A8, computed-coordinate and cube worker changes are applied in a deterministic, nonoverlapping order, with a frozen source input hash and clean rollback.
4. Cube six-face orientation is **not verified** in this lane because cube face sampling belongs to separate task `50768`; the acceptance item must be fulfilled by that owner / integration verifier.
5. Keep known working Pixman/softpipe fallback; never deploy, suspend, or promote renderer based on host checks.

**Disposition:** isolated patch and host evidence exist, but release/GLES2 hardware qualification is NO-GO until cross-worker integration and pixels are verified.
