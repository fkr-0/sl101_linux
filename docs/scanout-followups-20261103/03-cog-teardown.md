# Cog 0.18.5 teardown lifetime candidate — 2026-11-03

- OCP task: `SL101-LINUX-03-COG-TEARDOWN-LIFETIME-FIX-20261103-4C030C`.
- Native packet: `575970ad-c90b-4406-9839-13cc7b2e47c5`, independent review required.
- Pinned source: Cog tag 0.18.5, peeled `5d7c720e4f16360a0412a949a1a3f4209e81b9ec`, private tree `work/scanout-followups-20261103/cog-teardown/cog-src`.
- Patch: `patches/cog-0.18.5/teardown/cog-0.18.5-release-lifetime.patch`. Only Cog DRM renderer/header/platform; FBL07 launcher and other owners untouched.

## Evidence and invariant

Cog's WebKitWebViewBackend owns exportable destruction via GDestroyNotify; the DRM platform separately finalizes its renderer. Original renderer destructor attempts FDO releases, potentially after its exportable was freed. Original failed atomic flip leaks the allocated handler record. Pending flip callbacks hold raw renderer and buffer pointers. Original release clears the exported resource after dispatch, exposing a reentrant double-release window.

Candidate wraps FDO ownership in an explicit backend destroy notifier. Either backend destruction or platform finalization invokes the renderer stop hook while the exportable is still alive. Stop destroys its GLib DRM event source, frees pending flip callback allocations, detaches resource listeners and releases all remaining exports before freeing BO/FB; after this, renderer destruction is idempotent. Pending flip data is tracked and cleaned on commit failure, and release tokens are stolen **before** FDO dispatch. On resource destruction, queued handler references to that resource are nulled. Exportable destruction still occurs through WebKit's destroy notification, not suppressed.

## Reproduction and limits

Run `python3 -m unittest tests.test_sl101_cog_teardown -v`, `make test`, and `make check`. The Python test compiles a standalone lifecycle **model** and replays strict Git patch apply/reverse against the pinned source. These tests are **not Cog-linked fault injection**. Local Meson setup for Cog failed because host WPE WebKit development dependencies were unavailable; native Cog compile and ABI integration remain **unverified**. There is no authenticated symbolized target SIGTERM trace or installed Cog/FDO hashes yet. Source-level patch is a candidate, **not** accepted production fix.

Important unresolved hazards for independent reviewer: callback already in-flight on a different thread; the kernel may still scan a BO when resources are freed; first-mode-set property failure bookkeeping and mode-blob cleanup; multiple backends; failure to construct WebKit backend. Reviewer must ensure no release is skipped on reentrant Wayland destruction. Do not promote default based on this candidate.

## Local hashes and observed checks

Original Cog 0.18.5 source SHA-256: `cog-drm-renderer.h` `128f7fd98414cc4263fccf7f7d9d9ad9f285c3f6b459f8e4e4f26a63b3ebef07`; `cog-drm-modeset-renderer.c` `f53765967615f2d433d4261a79a35dda580fd6ffeecaba4d09b3b64940494b42`; `cog-platform-drm.c` `d5001fdf9cb012c6dd9054585bbe8a20c3be4a3d75818ecb931cf42a75d6a634`. Candidate patch SHA-256 `c727fb18e4ef00daf338d8b1016c50751565d99b28ddc67e345459908934e7b9`.

Local Debian ARMHF package archives: `cog_0.18.5-1_armhf.deb` SHA-256 `c3b698c9e3e8ab77a49e49abf1b40ef07e6c34fae52dedaa32511af00e792e6e`, `libwpebackend-fdo-1.0-1_1.16.1-1+b1_armhf.deb` SHA-256 `7eefdc578cd6278d540b98516a04cad3e7868ccd255081cd75fccdb03c52e078`. **Package archives are not installed shared object hashes or evidence of what Nura .106 ran**.

Observed host tests: `tests.test_sl101_cog_teardown`: 3/3 pass; `make test`: 247 tests pass (some existing test fixture intentionally prints a failed patch replay); `make check`: pass. The isolated host Cog Meson setup failed specifically on missing `wpe-webkit-2.0`, `wpe-webkit-1.1`, and `wpe-webkit-1.0` dependencies.

## November 5 source-extracted negative regression (HOLD)

`tests/test_sl101_cog_teardown_negative.py` compiles the **actual patched function bodies** of `release_buffer_exports()` and `destroy_buffer()` from the pinned private Cog source, substituting host-only DRM, GBM, GLib and FDO mocks. Under a deliberately reentrant FDO-release mock that destroys the same buffer before dispatch returns, AddressSanitizer reports `heap-use-after-free` when the outer `destroy_buffer()` continues to access `buffer->fb_id`. This is a source-grounded **counterexample** to the prior candidate's safety claim, not confirmation that target WPE/FDO follows precisely this callback sequence. Both the original standalone model and the new negative oracle pass, but their joint success does **not** qualify production teardown. Reproduction:

    python3 -m unittest tests.test_sl101_cog_teardown_negative -v

The negative test intentionally expects the sanitizer failure; it must become a positive real-callback, exactly-once teardown regression when the candidate is rewritten. Source patch remains unchanged, **HOLD**. A safe revision must detach resource listeners and invalidate buffer and flip references *before* synchronous FDO dispatch, establish ownership of callbacks already in progress, and prevent frame-complete/release callbacks from using a renderer after shutdown reentry. Destroying GLib's event source is not equivalent to draining kernel pending-flip userdata. Independent review must validate these invariants using patched callbacks and fault injection, followed by ARMHF link and serial device gates.

## Later serial qualification

After actual linked Cog build and independent review, sole graphics owner verifies Nura `.106` separately from Debian `.100`, exact source/build/installed .so hashes, backups, no shared launcher mutation and rollback. With physical supervision, collect clean shutdown, SIGTERM, pending and rejected flips, exactly-once release/destroy instrumentation, 60s soak, symbolized segvbt, KMS logs, actual pixel evidence and rollback status. Preserve labwc flock/shim HOLD. Producer's reported 262 flips, 2610 GR3D submissions and 20fps with CPU Skia are not teardown proof.
