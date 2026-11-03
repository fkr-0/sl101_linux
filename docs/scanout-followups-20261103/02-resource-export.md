# Resource export candidate — 2026-11-03

## Ownership and status

OCP `SL101-LINUX-02-RESOURCE-EXPORT-REVIEW-AND-PACKAGING-20261103-BAAC66`; native packet `30ea5045-c8ce-46c4-bf80-e04d02accb8b`. Host-only candidate; **not integrated, reviewed, deployed or hardware-qualified**. Nura .106 and Debian .100 are distinct. No live writes, GPU/KMS run, renderer changes or Mesa build on device were made.

## Evidence and immutable identities

| Artifact | Host SHA256 |
|---|---|
| `patches/mesa-25.0.7/0038-grate-resource-get-param-linear-modifier.patch` (original, untracked) | `ad257d04999bd72a6403e2585e02516d213bccb56bb49e92bea2097121635153` |
| `patches/mesa-25.0.7/0038-grate-stencil-state-fbl04.patch` (separate, preserved) | `2f1a94791011b148cae01201447a0ba54fdb97b9b5c7fa77b261cf21b924d6e1` |
| Grate current source `grate_resource.c` (already contains original callback) | `29ce187ee60118142da4ff42e91c6b6ae2fb35ab2c9dc9e730c7c11a37fafb7e` |
| Grate current `grate_resource.h` | `37925080f0fb378f8414e02970078f2bffa5f09ef62f6e142feb7a3cfb9722a0` |
| Follow-on `patches/grate-resource-export/0001-grate-linear-export-fail-closed.patch` | `f2b9666908de7370296e4a81757d4b611effe01f4172ad3f1c45b4384a48283d` |
| `fbl/evidence-kms-cog-gpu-example-org-20261103.png` | `5e16288261a399d8eb7e8e15ccc7f11b03843e41688962b447c9562b9c3fd323` |
| `fbl/sl101-fbdump.c` | `563a1b2828109d44f856e704c89ed923db2af249d78288b64ba3154a19ad7b1a` |

The producer reports a framebuffer image, 262 atomic flips, 2610 GR3D submits over 15 seconds, rAF ~20 fps and zero reported crashes/compile failures with CPU Skia enabled. The host has the image and capture-tool source, **not a linked authenticated running-device build ID, chroot binary hash, full timestamped DRM log, target package list or the original .bak hashes**. No claim of deployed byte identity follows from the image. The producer summary lists truncated chroot-library hashes (libEGL `41e52130…`, libgallium `e5bdf493…`, dri_gbm `6a23bf84…`) and backup patterns `*.pre-0035-20261103-142142.bak` / `libgallium-25.0.7.so.pre-0036-20261103-144044.bak`; these are not independent full-file hashes or installed provenance. Existing FBL notes also report banded geometry and Cog teardown defects; this is not general browser qualification.

## Mesa callback contract and defect analysis

Mesa 25.0.7 `pipe_screen.resource_get_param` is queried by DRI2 for NPLANES, STRIDE, OFFSET, MODIFIER, KMS/shared/FD handles. DRI2 rejects `DRM_FORMAT_MOD_INVALID` when querying modifier halves. The original driver returns true with INVALID for `resource->tiled`: success does not make an unknown modifier meaningful. Grate's internal allocator initializes `tiled=0`, whereas its imported BO path imports a stride from `winsys_handle` but discards the modifier. Implicitly advertising such imports as LINEAR is unsafe. The underlying GR2D and GR3D paths still branch on `tiled`; linear must be proved rather than assumed.

The follow-on candidate confines positive layout export to an existing BO, base plane/level/layer, one-plane nonbuffer nonarray 2D-like resource with nonzero pitch/height, and either locally linear allocation or an import carrying explicit LINEAR. Unknown imported modifiers and tiled resources are not re-exported as LINEAR. It widens the layer-stride multiplication to 64-bit before multiplication. For supported handle queries it delegates to the underlying Grate callback, preserving the provider's FD-return ownership contract: the successful caller owns the returned dma-buf FD. On failure no new handle value is published. No unconditional FD close was introduced by this patch.

**Unresolved review issues:** Exact import modifier policy (including implicit INVALID legacy imports), format-specific planes, bo allocation size versus pitch*height, supported layer/level layouts, KMS BO handle scope, and exporter synchronization still need upstream and off-device build integration review. The original import code does not validate positive stride, BO size, or all formats; this candidate limits export but does not retrofit complete import validation. The callback receives a non-null valid resource under the Gallium contract; comprehensive hostile-pointer resilience is not claimed. The callback C harness uses the extracted candidate function with stubs, not a full Mesa link or real kernel ioctl. Test outcomes must not be described as hardware proof.

## Host-only integration and qualification handoff

1. Freeze the source plus original patch hashes; note that two different patches are named `0038`. Preserve both original paths for traceability. Candidate integration order is original resource callback 0038, this follow-on candidate after it, and independently ordered stencil patch with a unique number coordinated by the series owner. **Do not rename, overwrite or renumber either existing 0038 here.**
2. Replay the original resource patch against a separately pinned pristine Mesa 25.0.7 source, then this correction with zero fuzz. Current tests strictly replay and reverse the correction from the observed already-patched Grate source and verify byte equality; this does **not** prove the pristine-series integration. Reconcile all prior generated Mesa differences before accepting full replay.
3. Obtain independent native review with exact source ABI, imported modifier semantics and successful/failed handle paths. Then build in an isolated off-device Docker/bwrap cross tree and record source commit, patch SHA256 manifest, cross compiler, sysroot, ARM binaries and linked `libdrm_tegra` hashes. Avoid shared generated Mesa tree edits.
4. A separately authorized serial live owner must verify Nura .106 target identity, installed/backup hashes, rollback, timeout and hardware capture with correct pixels. Verify tiled/unknown FD imports are rejected, exported linear framebuffer scanout survives animation, teardown and concurrency, and renderer fallback remains working. Do not conflate Nura .106 with Debian .100.
5. Keep the default HOLD until combined candidate integration and independent review, serial KMS/Wayland/pixels/browser/teardown/rollback qualification. The existing labwc flock/shim is HOLD; an inert sentinel is not a lock.

### Test commands

`python3 -m unittest -v tests.test_sl101_resource_export` compiles a C harness against the actual candidate callback extracted after strict replay and checks branch and overflow semantics. `make test` and `make check` are project-wide host gates. Logs are retained under `work/scanout-followups-20261103/resource-export/`.
