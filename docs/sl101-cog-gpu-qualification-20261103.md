# SL101 Cog/WPE GPU qualification gate — 2026-11-03 (lane 08)

**Decision: NOT QUALIFIED.** This is a host-side acceptance contract, not a new hardware test or permission to promote GLES2 as the default. The existing labwc pixman baseline must remain untouched.

- OCP: `SL101-LINUX-08-PROMPT-QUALIFICATION-GATE-20261103-06BCEF`
- Canonical project: `sl101_linux`; owned scope: this report and `tests/test_sl101_cog_gpu_gate_fbl08.py`
- Exact prospective target (reconfirm live before any test): Nura SL101 `192.168.23.106`, kernel `7.0.1-postmarketos-grate`; Debian chroot `/opt/sl101-cog-wpe-debian`; private Mesa `/opt/grate-mesa25-clean/lib/arm-linux-gnueabihf` *inside chroot*.
- Sources: `docs/sl101-wpe-fdo-egl-investigation-20261103.md` (§5 older zero-rAF observation), user-supplied 2026-11-03 Mesa 0035/0036 and KMS trace findings (unverified independently in this lane). Historical evidence is **not** a current pass.
- Coordination: lane 01 exclusively owns live graphics/session/deployment until durable explicit handoff; lane 08 performs **no live test or mutation** before it, and only after relevant fixes and reviews. Lane 06 owns build/series/deploy tooling. Do not touch `build/mesa-grate-clean`.

## Immutable evidence gate

All eight checks are required. `PASS` requires independently inspectable, dated artifacts from the *same* exact build, target and test session; missing/stale/mismatched evidence is `UNKNOWN` and fails closed. `FAIL` is a demonstrated violation. Two-dimensional result: `gpu_submitted` is not `gpu_presented`, and GPU composition is not GPU Skia raster.

| # | Criterion | Concrete PASS evidence | Present decision |
|---|---|---|---|
| 1 | WebProcess identity | PID/start time, process environment showing `MESA_LOADER_DRIVER_OVERRIDE=grate`, `/proc/<PID>/maps` mapping chroot `libgallium-25.0.7.so`, and SHA256 of mapped inode/build artifact (capture namespace/root mapping) | UNKNOWN; old mapping reports do not bind a current process |
| 2 | GR3D ioctl oracle | `strace -f -tt -e trace=ioctl -v` with per-PID `DRM_IOCTL_TEGRA_SUBMIT` (0x48) success/return codes, WebProcess identity, timestamps, and independent frame/visible pixel timeline. Demonstrate sustained submissions over successive frames; **never** equate one ioctl with one frame | PARTIAL historical: 22 WebProcess submits reported in KMS, no frame/pixel correlation |
| 3 | Shader correctness | Captured full logs and `GRATE_DEBUG=tgsi` dumps, no `compile failed` or `dropping draw` on all three pages (example.org, CSS animation, image+text); include compiler failure count and hashes | UNKNOWN; reported zero on a single KMS CPU-Skia run |
| 4 | Frame scheduling | Reliable `ThreadingHTTPServer` fixture (§5 investigation) on each test page, JSON with `frames > 0` over 10 seconds; separate timer/result receipt and URL; rAF alone does not prove GPU | FAIL historical: prior GPU fixture `frames=0`; new comparison required |
| 5 | Correct pixels | GPU/software matched-scene PNGs, target/display/resolution/timestamps and SHA256, pixel comparator with documented channel/alpha handling, tolerance, masks and diff statistics. Record renderer and capture backend (`grim` labwc or FB KMS) | UNKNOWN; KMS atomic `EINVAL` blocks scanout |
| 6 | Stability | Continuous 10-minute timestamped scrolling/reloads, stable WebProcess PID+start time and labwc PID, no `Crash!`, dmesg GR3D fault, renderer fatal errors or WebProcess respawn | UNKNOWN; 0 reported crashes during a short KMS trial is insufficient |
| 7 | Rollback | Record all original library paths+hashes, backup paths+hashes, matched restored hashes, repeat baseline behavior, and preserve pixman default. Rehearse only after lane 01 handoff, dry-run, identity, backup and recovery approval | UNKNOWN; backup filenames are not a rollback rehearsal |
| 8 | Audit/check-in | Archive manifest with SHA256 hashes, build provenance, results, independent reviewer identity/decision, `orh project checkin --agent <agent>` receipt, and report/commit path | IN PROGRESS; host report alone is not live qualification |

## Blockers and dependencies

1. Lane 01: decode atomic `MODE_ATOMIC -EINVAL` request/driver rejection and failed-buffer ownership without presuming cause. Require passing scanout, valid buffer release, and proven pixels in KMS; hand off live device explicitly.
2. Lane 02: replace asymmetric render-node flock with completion/fence-safe lock lifecycle, including submission errors; independently review before lane 05 labwc testing. Releasing immediately after asynchronous submit is **not** an accepted fix.
3. Lane 03/04: preserve CPU Skia raster as default; DP2 and stencil state must have independent proof; advertising S8 EGL config does not prove stencil correctness.
4. Lane 05: obtain actual labwc path after reviewed lock fix; no compositor/session changes before lane 01 handoff.
5. Lane 06: own separate reproducible build/deploy series, known hashes, exact device identification, dry-run, backups, and rollback. No lane-08 series edit.
6. Lane 07: review Cog DRM failed-buffer release behavior and crash path before stability or rollback claims.
7. Lane 08: after all relevant reviewed fixes and live ownership handoff, execute complete protocol; request independent reviewer before promotion.

## Evidence collection contract (run only under authorized device ownership)

Create one run directory under ignored `work/` or an explicitly authorized device `/tmp/`, with a unique run ID; never check in large logs, captures, device secrets, build blobs or generated binaries. Capture process tree/start time, env and maps **before** tracing; archive `/proc/<pid>/maps` and hash the library resolved through the process root/chroot. Preserve strace `-f` PID mapping and timestamped ioctl returns. Identify successful `TEGRA_SUBMIT` by decoded request **and** return, not by string counting alone; correlate independent frame counters, captures and submissions in comparable time windows. Capture TGSI shader dumps, WebProcess and Cog logs, RAF JSON, pixel pairs, decoder/comparator output, ten-minute process/dmesg logs, and rollback receipts. Do not edit kernel command line to `drm.debug=0` on cleanup: save and restore its exact prior value with a `trap/finally` even on error.

Example *read-only* host-side decision input (not a claim of measured results):

```json
{"identity": false, "ioctl": false, "shader": false, "frames": false, "pixels": false, "stability": false, "rollback": false, "audit": false}
```

Check strictly with `python3 tests/test_sl101_cog_gpu_gate_fbl08.py --receipt /path/to/receipt.json`. Each property becomes true **only after** its referenced supporting artifacts have been verified by the operator and independent reviewer. A bare Boolean receipt is an assessment index, not substitute evidence; include `evidence` hash manifest alongside it. Exit 0 means the index is complete, **not** independent validation of artifact authenticity. A missing receipt or any non-true criterion returns nonzero. Production promotion also needs the mandatory independent review and live device signoff.

## Current result

**BLOCKED / NOT QUALIFIED**: historically reported 22 GR3D submissions do not demonstrate displayed frames; KMS `EINVAL`, broken Cog release path and labwc lock protocol prevent qualification. No lane-08 live tests, library replacement, screenshot, 10-minute soak, rollback rehearsal or independent review has been performed here. `make test`, `make check` and host-only gate unit tests are separate from hardware certification.
