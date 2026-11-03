# SL101 lane 06 — chroot Mesa source and deployment reproducibility

**Canonical OCP task:** `SL101-LINUX-06-PROMPT-BUILD-REPRODUCIBILITY-20261103-43D8D2`  
**Canonical project:** `sl101_linux`  
**Date:** 2026-11-03  
**Status:** **Candidate implementation; release/deployment NO-GO pending byte-equivalent replay and independent review.**

## 2026-11-03 revision safety hold (OCP 7F1F5A)

Independent review requested changes. As a bounded fail-closed mitigation, `scripts/sl101-chroot-mesa-deploy.sh` now rejects every `--apply` invocation (exit 3) **before SSH or reading manifest inputs**, regardless of any supplied handoff text. The unverified per-file activation/rollback prototype was removed entirely; a genuine authoritative owner/lease/target check and atomic-set activation or fully verified rollback transaction remain prerequisites to restoring apply. Dry-run remains available with identity checks. A host adversarial test provides a fake matching handoff plus a fake SSH executable and asserts no remote operation occurs.

**Still blocked / no qualification claim:** the immutable intended production source snapshot with before/after hashes, attribution for the nine differing Grate files, zero-fuzz byte-equal replay, clean isolated Docker cross-build and ARM glibc ELF interpreter/DT_NEEDED provenance have not been established. The mutable shared tree and pending lane 01/02/03 patches must not be treated as authoritative production inputs. No production files copied or modified, no live deployment, and no host musl prefix writes. This revision does not claim atomic activation or rollback testing because activation is disabled. A bounded scope amendment is necessary before persisting new frozen source artifacts under work/ or introducing additional patch files, and independent review is still required.

## Boundaries

This lane owns `patches/mesa-25.0.7/series`, `build/mesa-grate-clean/build.sh`, `scripts/sl101-chroot-mesa-deploy.sh` and its own `tests/test_sl101_chroot_mesa_lane06.py`. It has not touched the live SL101, restarted labwc, written host Mesa's prefix or modified the shared `build/mesa-grate-clean/mesa-25.0.7` tree. Candidate replay was built under `/tmp/sl101-lane06-replay` and is not a deployment source.

The existing `container-prep.sh` remains unchanged for isolated incremental builds. Do not concurrently operate the shared generated source/builddir. Stage a separate copy of `build/mesa-grate-clean` and build output for each lane.

## Pin inventory

| Source | SHA256 / deterministic digest |
|---|---|
| `build/mesa-grate-clean/mesa-25.0.7.tar.xz` | `592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6` |
| `build/mesa-grate-clean/grate-libdrm.tar.gz` | `febe85e2c87af617e2c183943b74b2cfe1dc1797521790faedb3783a7a3c2294` |
| `work/sl101-cog-gpu-20261004/build-system/mesa25-grate-build-system.patch` | `60c75af505179bb1fd885d55fb6378c02a6cdd60e079f1e0c379003ce3f24551` |
| `work/sl101-grate-production-20261004/grate-src` | `dd6b385a32425ab2959e61f66462e69d47bea343b6c604aed512748f31b2948e` |
| `tmp/sl101-nura/gpu-egl-20260930-r2/tex-split-diag/build-pseq-final/mesa-25.0.7/src/gallium/winsys/grate` | `2483856fad8c143adf238acf2e792346aaabc03002d81d057f04684dbc03e5b1` |

Directory digests are the SHA256 of sorted `sha256sum` lines for each file, with paths relative to the directory. The series itself stores ordered SHA256s of **10 currently cleanly applicable patches**. These are not an assertion that the other patch artifacts are irrelevant; many are already incorporated in the production Grate source, and the remaining differences require explicit reconciliation.

## Host replay evidence

A pristine Mesa 25.0.7 archive was extracted to a distinct `/tmp/sl101-lane06-replay/mesa-25.0.7`; the verified Grate Meson integration patch was applied and the production Grate driver and winsys were copied. All ten candidate series patches applied using GNU `patch --batch --fuzz=0 -p1`. Individually, both `0035` and `0036` passed isolated host zero-fuzz checks. A recursive source comparison ignored `builddir` and identified **nine differing Grate source/build-system files**, namely:

```text
src/gallium/drivers/grate/fp/fpir.h
src/gallium/drivers/grate/fp/tgsi.c
src/gallium/drivers/grate/grate_draw.c
src/gallium/drivers/grate/grate_resource.c
src/gallium/drivers/grate/grate_screen.c
src/gallium/drivers/grate/grate_state.c
src/gallium/drivers/grate/grate_state.h
src/gallium/drivers/grate/grate_texture.h
src/gallium/drivers/grate/meson.build
```

Those remaining differences prove that the candidate series **does not yet reconstruct the mutable shared tree**. Build success cannot substitute for this equality gate. Generated Meson, Python cache and source-`.orig` noise were separately excluded from the nine-file comparison. Source divergence may also be affected by ongoing parallel graphics lanes; coordinate a frozen snapshot and review exact differences before pinning additional patches. In particular, neither FP DP2 work (lane 03) nor cross-process serialization (lane 02) may be silently integrated or overwritten.

## Build and deployment contracts

`build.sh` now checks SHA256 of Mesa archive and Grate build-system patch, and hashes driver/winsys source trees before deleting its isolated Mesa extraction; it applies the ordered hash-pinned series, exiting on missing entries, changed hashes, fuzz failures or rejected hunks. **This makes the candidate input replay deterministic, not release-qualified.** Its existing libdrm build and container assumptions still warrant independent clean-build verification.

`scripts/sl101-chroot-mesa-deploy.sh` is **dry-run by default**, accepts a separate two-column SHA256 artifact manifest and an exact 32-character SD CID, verifies the running kernel `7.0.1-postmarketos-grate` and selected SD block device, and targets only:

```text
/opt/sl101-cog-wpe-debian/opt/grate-mesa25-clean/lib/arm-linux-gnueabihf
```

It does not write to `/opt/grate-mesa25-clean` in the host system. An actual `--apply` additionally requires an explicit durable lane-01 handoff record. Apply uses a staging directory, re-verifies artifacts on-device, creates timestamped `.bak` copies, atomically replaces files and attempts automatic rollback on an error. The script never restarts labwc and does not treat deployment as GPU pixel proof. Exact device CID and production artifact manifest were **not available/qualified** in this lane; no live apply has occurred.

Create a manifest only for the specific known-good, inspected artifact bytes, for example from the isolated output library directory:

```sh
cd build/mesa-grate-clean/output/opt/grate-mesa25-clean/lib/arm-linux-gnueabihf
sha256sum libEGL.so.1.0.0 libgallium-25.0.7.so gbm/dri_gbm.so > /path/to/approved-chroot-manifest.sha256
```

This demonstrates the manifest format, **not** authorization to deploy those unqualified files. Deployment additionally requires approved identity, handoff and reviewed qualification.

## Verification and next actions

- Host isolated tests: all ten selected series patches apply in order with `--fuzz=0` against isolated pinned source fixtures; `0035` and `0036` also apply individually. SHA inventory and shell syntax checks pass.
- `make test`: **214 tests passed** after the final lane-06 test addition; `make check`: passed.
- No shared-tree rebuild, chroot library replacement, live GPU test or session restart was attempted.

**Blockers:** reconcile the nine source differences and patch overlaps against a frozen production source snapshot; produce a complete byte-equivalent replay; independently review the deployer's atomicity/rollback and target gate; run an isolated Docker clean build and inspect glibc ARMHF ELF dependencies; obtain lane-01's explicit live-device ownership handoff before any apply. Preserve mandatory independent workflow review before promotion.
