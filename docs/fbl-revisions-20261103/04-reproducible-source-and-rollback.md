# FBL06 continuation — frozen inputs, replay and off-device qualification

**2026-11-03 · OCP:** `SL101-LINUX-05-FROZEN-SOURCE-BUILD-20261103-AA7854`

**Native packet:** `39fb32ea-f966-48cc-a02a-cc4eb30437ea` (admitted scope)
**Status:** **BLOCKED / NO-GO** for full source reconstruction and ARMHF release. This continuation does not amend or reopen original packet `40ef5e18`. Independent review remains required.

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
