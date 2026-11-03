# FBL06 continuation — frozen inputs, replay and off-device qualification

**2026-11-03 · OCP:** `SL101-LINUX-05-FROZEN-SOURCE-BUILD-20261103-AA7854`

**Native packet:** `39fb32ea-f966-48cc-a02a-cc4eb30437ea` (admitted scope)
**Status:** frozen observed-source reconstruction and experimental ARMHF Docker build verified in the revision below; **NO-GO** for accepted producer history, device runtime qualification, and ARMHF release/deployment. This continuation does not amend or reopen original packet `40ef5e18`. Independent review remains required.

## Safety boundaries

- This lane performs only host-side snapshotting, replay, an isolated Docker build attempt, and tests.
- **No device writes, SSH mutation, GPU execution, compositor changes, reboot, suspend, or renderer promotion occurred.**
- `scripts/sl101-chroot-mesa-deploy.sh` is restored to executable mode `100755`; all `--apply` invocations still return 3 **before SSH**, including a fabricated handoff.
- Host root filesystem had ~2.5 GiB available; Docker experiment used staged inputs under tmpfs `/tmp`, `--network none --cpus 2 --memory 4g --memory-swap 6g --pids-limit 256`, with `ninja -j2`. No concurrent shared generated tree was overwritten.

## Frozen source and provenance

Private ignored evidence: `work/fbl-revisions-20261103/04-reproducible-source-and-rollback/`. Two independent passes of sorted file SHA-256 lines were **byte-identical**; copy verification passed for every file.

| Source | Recorded tree-manifest SHA-256 | Meaning |
|---|---|---|
| `work/sl101-grate-production-20261004/grate-src` | `dd6b385a32425ab2959e61f66462e69d47bea343b6c604aed512748f31b2948e` | Local production-labelled source, **not proven upstream commit** |
| `tmp/sl101-nura/gpu-egl-20260930-r2/tex-split-diag/build-pseq-final/mesa-25.0.7/src/gallium/winsys/grate` | `2483856fad8c143adf238acf2e792346aaabc03002d81d057f04684dbc03e5b1` | Local winsys source |
| `build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate` (excluding *.orig, *.rej) | `1520a2aba81033818345299a739cc6a7eb1f1b6ea7b012f37cd93c7aa5a228df` | Frozen observation of **mutable** shared source; not approved integration baseline |

These are **manifest digests**, computed as SHA-256 of GNU sha256sum output with relative sorted file paths, not Git tree hashes. Files are copied to `snapshot/grate-driver`, `snapshot/grate-winsys`, and `snapshot/shared-driver-observed` under the private evidence directory. Original timestamps are retained. The provenance does **not** establish an upstream fork revision or a production binary's exact compilation inputs.

Fixed archives: Mesa 25.0.7 `592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6`; grate-libdrm `febe85e2c87af617e2c183943b74b2cfe1dc1797521790faedb3783a7a3c2294`; Grate Meson integration patch `60c75af505179bb1fd885d55fb6378c02a6cdd60e079f1e0c379003ce3f24551`.

## Zero-fuzz replay versus source acceptance

A new **isolated** Mesa tar extraction, verified Meson patch, frozen production-labelled driver/winsys copies, and the existing ten ordered hash-pinned patches replayed successfully with `patch --batch --fuzz=0 --no-backup-if-mismatch -p1`.

Comparison against the separately frozen observed shared driver still finds **exactly nine divergent paths**:

```text
fp/fpir.h
fp/tgsi.c
grate_draw.c
grate_resource.c
grate_screen.c
grate_state.c
grate_state.h
grate_texture.h
meson.build
```

Per-file unified differences are preserved under `evidence/diffs/`, with the complete path listing in `evidence/replay-vs-observed.diff`. They include absent KILL lowering in the observed tree, texture-pitch and resource logic differences, screen/state deletions, and Meson dependency differences. Differences **must not be blindly applied in either direction**: the source-labelled 'production' directory, the observed mutable tree, and pending FP DP2 / GR3D lock / modifier producers do not share verified ordered ancestry. In particular the candidate series currently contains fragments not present in the observed shared driver. The nine paths are inventoried and attributable to concrete diff hunks, **but no accepted producer-commit attribution or complete intended-source replay is proven**.

Consequently **no new `patches/mesa-25.0.7/reproducibility/` patch is promoted into `series`** and no false byte-equality claim is made. Accepted fixed producer hashes must first be identified and their integration deltas recorded. Pending DP2, locking and modifier candidates remain **held/excluded**.

## Docker ARMHF/glibc attempt

Used existing local image `mesa-grate-build:latest` with image ID `sha256:b1cda264467478f78d1e8c58bcde065c3531cbffd70f382c2c84ce07ea619959` (no immutable registry digest). Cross file selects `arm-linux-gnueabihf-gcc`, ARMv7-A `-mfpu=vfpv3-d16 -mfloat-abi=hard`, and no explicit NEON flags. Compiler reported GCC 12.2.0, Debian bookworm image. Inputs staged in isolated `/tmp/sl101-fbl06-build.*`; Docker networking disabled. The Meson configuration **failed** because the image contains `wayland-protocols 1.31` but Mesa tried obtaining `wayland-protocols 1.38` from GitLab. No network fallback was allowed. See `evidence/docker-candidate-build.log`.

As no *new* successfully linked output exists, ARMHF ELF interpreter / VFP-no-NEON attributes / `DT_NEEDED` and full glibc/sysroot closure **remain unverified**. Neither pre-existing `build/mesa-grate-clean/output` binaries nor older production libraries substitute for a clean-build attestation. Pin a suitable offline protocol dependency with digest and supply an audited cross sysroot before retrying.

Build recipe hardening: all Ninja invocations use `-j2`; missing Mesa archive fails without `wget`; Meson uses `--wrap-mode=nodownload`; this prevents silent unpinned network-fallback dependencies.

## Required acceptance gates

1. Obtain reviewed accepted producer commits and annotate each of the nine diffs with ordered ownership; reconstruct the **intended** frozen source byte-for-byte with zero fuzz, no rejects, and immutable hashes.
2. Qualify offline ARMHF/glibc Docker toolchain, libdrm, sysroot and Wayland protocols with exact version/digests and complete build logs. Record ELF machine, interpreter (for executables), ARM attributes, `DT_NEEDED`, runtime transitive resolution and evidence against NEON.
3. Obtain native verified ownership/target authority **and** atomic whole-bundle activation or independently proven full rollback before even considering an apply-capable deployer. **Actual apply remains prohibited in this phase.**
4. Obtain mandatory independent code review. Nothing in this report constitutes deployment approval.

Focused adversarial tests and `make test` / `make check` logs are in the private evidence directory.

## Independent review revision — frozen observed-tree experiment (2026-11-03)

Following the independent `request_changes` on commit `41d5743`, a **separate experimental observation target** has been reconstructed. The official `patches/mesa-25.0.7/series` remains unchanged; no patch was accepted as functional/prod-ready.

- The original ten hash-pinned candidate patches replay with `--batch --fuzz=0 --no-backup-if-mismatch` onto a fresh Mesa 25.0.7 extraction, Grate build-system patch and two frozen snapshots.
- Nine divergent driver paths are represented by a single *held observational delta* at `patches/mesa-25.0.7/reproducibility/0001-held-observed-driver-delta.patch` (SHA-256 `e6231129776cdc5e4da47fada7cb487395d8ea3c1a25b5b4ab8ab90dab386a89`), with its distinct `series.observed-held` inventory. This is a delta from the existing candidate replay to the frozen **local observed snapshot**, not an authored commit history, accepted upstream series or proof of production origin.
- A fresh zero-fuzz dry-run followed by strict application showed exact file-content and path equality to the frozen observed driver after discarding `grate_screen.c.orig`, a transient patch backup in the temporary candidate tree. The target file manifest is `1520a2aba81033818345299a739cc6a7eb1f1b6ea7b012f37cd93c7aa5a228df`, captured in two identical hash passes earlier in this packet.
- `build/mesa-grate-clean/build.sh` reconstructs the observed local tree **only with** `FBL06_EXPERIMENTAL_OBSERVED=1`, then checks the full observed manifest. The default never applies this held patch. Pending DP2, locking, modifier, and other unaccepted producers remain out of the canonical production series; the held delta has **no independently verified functional or commit attribution**.
- The reviewer-provided offline Wayland protocols 1.38 archive matches pinned SHA-256 `ff17292c05159d2b20ce6cacfe42d7e31a28198fa1429a769b03af7c38581dbe`, identical to the Mesa `subprojects/wayland-protocols.wrap` pin. The build script's optional `FBL06_WAYLAND_PROTOCOLS_ARCHIVE` feeds this cache after fresh extraction, with `--wrap-mode=nodownload`. Host build is isolated under `/tmp/sl101-fbl06-isolated-build.*` with `--network none --cpus 2 --memory 4g --memory-swap 6g --pids-limit 256` and `ninja -j2`; no unpinned SDK downloads.

**Safety status remains NO-GO for live installation**: executable mode `100755` is retained; `--apply` is refused before remote access. Local source byte equality does not demonstrate GPU correctness, full runtime closure, or any deployment authorization. See private `evidence/revision-*` files for the build and tests; update exact ELF/link evidence only after the build has exited successfully.

### Completed experimental ARMHF build and static ELF audit

The **second**, idle-timeout-disabled isolated Docker run finished successfully. Build log: `evidence/revision-docker-build-retry.log`; prefix staged only in `/tmp/sl101-fbl06-isolated-build.*/build/output/opt/grate-mesa25-clean`. The first revision run was externally terminated by ws-bridge's idle-output timeout during compilation, not a compile error. No generated build tree in the shared checkout was touched.

Image identity: `sha256:b1cda264467478f78d1e8c58bcde065c3531cbffd70f382c2c84ce07ea619959` (`mesa-grate-build:latest`, local tag; registry provenance not established). Container Debian bookworm ARMHF cross-GCC 12.2.0 with glibc 2.36 and libdrm 2.4.114; `armhf-cross.ini` sha256 `41d73d4552dde8b37a06b5966a9e4d16a539f36825a79d88cd282ebe9e1befaa`. Exact script sha256 `a098366778335c3ae82cf71ec616c5affaa4d54c6ad85c0ba296941f23a59c14` (see evidence). Protocols 1.38 came from the reviewed hash-matching offline tarball, not the image's older 1.31 package.

Six installed ELF regular files were inspected with `readelf -h`, `readelf -A`, `readelf -l`, `readelf -d` and SHA-256 recorded in `evidence/revision-elf-audit.txt`. All are **ELF32 little-endian ARM EABI5 hard-float**, CPU architecture ARMv7, FP architecture **VFPv3-D16**, VFP-register calling convention. No `Tag_Advanced_SIMD_arch` is present; a disassembly grep of the large `libgallium` image found no selected NEON opcode families. This does **not** prove every instruction of every binary has been exhaustively vetted. Outputs are shared libraries so they have no ELF `PT_INTERP`; their `DT_NEEDED` includes `ld-linux-armhf.so.3` in the glibc runtime closure. The experimental image contains `libgallium-25.0.7.so`, `libEGL.so.1.0.0`, `libgbm.so.1.0.0`, `libGLESv2.so.2.0.0`, `libdrm_tegra.so.0.0.0` and `gbm/dri_gbm.so`.

`evidence/revision-dependency-closure.txt` resolves all transitive `DT_NEEDED` dependencies for **17 ELF objects** against the isolated output and container's ARMHF sysroot, with **zero unresolved names** (including `libstdc++.so.6` from `/usr/arm-linux-gnueabihf/lib`). This is *builder-sysroot static closure only*, not proof the SL101 target has the same libc, loader, GLVND/Wayland stack, or correct runtime resolution. No target executables or `PT_INTERP` artifacts were generated. All post-revision tests pass: 10 focused lane06 tests, `make test` 234 tests, `make check` Python compilation; evidence under `evidence/revision-*-final.log`.

**Integration delta/hold:** The nine-file patch is a reproducible local observation, not a reviewed producer commit. It may reverse some later candidate changes because the shared observed tree did not include them. It is intentionally only a distinct opt-in experiment, not a production series update. No DP2/lock/modifier candidate or new driver semantics has been approved here. No deployment/`--apply`/renderer activation is permitted. Independent code review and separately authorized device qualification are required before any promotion.
