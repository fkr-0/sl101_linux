# SL101 Nuraloumi and EGL progress — 2026-10-02, 06:51 CEST

**Keep labwc/pixman. No EGL desktop promotion yet.** Nuraloumi is running on
hardware, independently of GPU acceleration. A corrected EGL build exists,
but its texture-layout correction and deployment bundle still need review,
followed by successful device pixel tests.

## Nuraloumi

Live tablet `root@192.168.23.106`: kernel `7.0.1-postmarketos-grate`, labwc PID
32231 with `WLR_RENDERER=pixman`. Panel PID 15171 runs from
`/root/.local/opt/nuraloumi-staging/panel-live-final`, approximately 9.7 MiB RSS.
The operator screenshot demonstrates visible panel/system menu, Wi-Fi state,
Bluetooth state, brightness, battery and clock. It does not prove every action.

Fresh current-tree `cargo test --workspace --locked`: 132 passed; strict
`cargo clippy --workspace --all-targets --locked -- -D warnings`: passed.
Source has native Cairo/wl_shm/layer-shell presentation and active
foreign-toplevel window-control integration. Independent ARMv7 strict-font
hardware evidence is documented in the Nuraloumi qualification tree.

Canonical Wayland, providers and xtask tasks are terminal complete. Core,
Cairo and shell remain marked running; workspace packet progress is richer than
those markers (18 completed, 4 active, 1 awaiting review at this snapshot).
Cross-build continuation still tracks clean-checkout Cargo.lock reproducibility.

`wpctl status` under the live root XDG runtime reports `Could not connect to
PipeWire`, and no PipeWire/WirePlumber process was found. This explains the
panel's unavailable speaker control; earlier ALSA playback success remains a
separate sound-path result. Suspend/resume, repeated popup endurance, all touch
corners and physical keyboard parity have not been freshly qualified here.

## GPU lanes

- Texture: reviewed source handoff packet ba230d7e completed. A subsequently
  discovered resource-layout defect requires correction packet d0b5c119:
  Mesa requests combined SAMPLER_VIEW|RENDER_TARGET; the old driver accepts it,
  allocates 32-byte render-target pitch for a 2x2 texture, but its sampler view
  requires tight 8-byte pitch and returns NULL. The correction rejects unsupported
  combined bindings, allowing Mesa's sampler-only fallback. Host contracts and
  actual ARMv7-musl compile pass; independent correction approval is pending.
- Arithmetic: FP20 high-word-first payload, varying N -> export N+1 and truthful
  temporary/instruction limits are implemented. Fresh independent rerun of
  fp-pack, vp-pack, limits and TGSI-lowering passes. Formal independent final
  approval is not confirmed by this review; no hardware arithmetic readback proof.
- EGL: active owned packet 76c01e41 integrated the texture handoff, built musl
  Mesa and ran a real offscreen probe. Run 1 returned 139 after EGL 1.4 and 2x2
  texture creation. No new dmesg GPU fault was recorded; this does not establish
  useful GPU rendering. A second candidate library e512e4d1... contains the
  binding correction and is staged in an isolated /opt prefix. Device acceptance
  is pending, and review explicitly holds qualification until correction approval.
- Review: active oversight found the layout issue, missing per-run preflight/lock
  receipts, an integration patch containing only its message and no diff hunks,
  and an install prefix not equal to the finished artifact hash. Correct these
  provenance defects before accepting deployment evidence.

Old candidate-2 texture readback was uniformly yellow and its headless labwc
recorded GR3D timeouts/resets. The newest build has not superseded those failures
with passing texture/alpha/arithmetic pixels, EGL window swaps and endurance.

Canonical GPU continuation tasks still show queued even though the texture
packet is completed and EGL work is active. Existing notes explicitly correlate
those packets/tasks and request idempotent workflow reconciliation. Do not
redispatch these apparent queued entries: that would duplicate active work.

## Next acceptance

Review the narrow layout correction; regenerate a real replayable patch and a
hash-consistent immutable bundle; record fresh device identity/power/DRM and
lock acquisition; run offscreen texture/alpha pixels. Integrate arithmetic only
after its independent approval, then qualify arithmetic readback and real EGL
window swaps before any bounded compositor test. The existing pixman desktop,
Nuraloumi and VNC remain usable during this work. This review made no GPU,
compositor, kernel or boot changes.

## Operator snapshot

Frozen stats at 2026-10-02T04:47:20Z. Previous durable review lower bound was not
reliably recovered; interval flows are unknown. Canonical queue: 44 queued /
44 runnable. Four live windows have 1–14 tabs (17/window configured, 68 total).
Rate: 131/300 operations per five minutes, underrun; admission open.
Semantic sample reports 4 generating, 0 idle/ready, 0 error, 0 waiting and
2 complete, but whole-fleet coverage was not established: fleet-wide counts are
unknown. Dispatched/enqueued/chained/legacy-promoted interval counts: unknown.

Evidence: `tmp/sl101-nura/gpu-egl-20260930-r2/egl/evidence/texture-r1/`,
`texture-layout-fix/evidence/`, `arithmetic/artifacts/handoff.json`, live
`.wsbridge:sl101-grate-egl` / `.wsbridge:sl101-gpu-egl` notes and canonical OCP
state. Host check logs: `/tmp/nuraloumi-review-20261002-{tests,clippy}.log`.
