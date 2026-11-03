# Lane 07 — Wayland DMA-BUF feedback correctness, 2026-11-03

**Canonical task:** `SL101-LINUX-07-WAYLAND-FORMAT-FEEDBACK-20261103-0EAAF9`.
**Disposition:** concrete **WPEBackend-fdo RFC candidate series, HELD**; no Mesa MR; no deployed/activated graphics or browser changes. Publication not authorized. This is host qualification and an ownership investigation, not live-device validation.

## Ownership verdict

- **Verified WPEBackend-fdo defect:** the version-4 `get_surface_feedback` handler in release 1.16.1 creates no feedback resource. A client destroying its nonexistent object disconnects with protocol `invalid object`. This defect is already reported in [issue #207](https://github.com/Igalia/WPEBackend-fdo/issues/207) and addressed by open [PR #208](https://github.com/Igalia/WPEBackend-fdo/pull/208); the lane's first patch is an independent candidate, not a new submission to duplicate that PR.
- **Verified WPE source contract concerns:** version-4 global bindings still send legacy modifier events, which v4 forbids; `initMainDevice` may return without device bytes; `initFormatTable` can leave no usable mapped format table on zero EGL formats; yet the v4 global is created. The second WPE patch gates v4 on available feedback data and prevents legacy v4 events. This is an **RFC hypothesis** about safest fallback behavior, not proof it resolves actual browser failure.
- **Mesa NOT established defective:** upstream Mesa's bitmap is a compositor-advertisement filter for `EGL_WINDOW_BIT`, while valid driver formats may retain `EGL_PBUFFER_BIT`; standalone surfaceless configuration is separate. An EGL render node fd alone cannot authorize any FourCC/modifier. The older `0031` accept-all bypass is rejected, not incorporated. The current main default feedback `done` callback is empty and the initialization uses a roundtrip; a delayed/incomplete update remains a candidate for targeted Mesa-linked testing, not an established parser defect.
- **Physical first-buffer cause unresolved:** the older capture did not demonstrate complete WebProcess startup feedback, selected fourcc/modifier/stride, actual gbm/DRI allocation, `zwp_linux_buffer_params_v1` import or pixel presentation. Do not conflate Cog's outer Wayland connection with the WPEBackend-fdo internal server. GLES2/EGL initialization alone is insufficient proof.

## Immutable sources and dependencies

- WPEBackend-fdo `https://github.com/Igalia/WPEBackend-fdo.git` tag `1.16.1` -> commit **`fc6f3d428962b34e1937aaa6bf66bcba92243da0`**; latest upstream `HEAD` sampled **`84492327673fa0dedfa4fa0ab9488bed1763a5a8`**. At these refs, `src/linux-dmabuf/linux-dmabuf.cpp` has identical SHA256 `8c0b10f7890234b3f2f132c9e1849f067f9252fd350131e1a31d7bdb86912f75`. Do not assume unrelated current WPE files are unchanged.
- Mesa official **25.0.7** release archive SHA256 **`592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6`**; PGP signature not independently verified here. Independently pinned current Mesa mirror Gitiles commit **`08e7afcd25aa4c1937865cff3e8665b7df86141a`**, `src/egl/drivers/dri2/platform_wayland.c` SHA256 **`c889e542e568a86848faccb6e4ab8bc1b2bbc2eafaf686244298befa35ae93c5`**. These are Mesa identities; enclosing SL101 Git SHA is **not** a Mesa revision.
- Official `wayland-protocols` 1.49 commit `ee78491a237eaff9389a0ccf8680521d074407d3`, stable linux-dmabuf XML SHA256 `2735bb4589cbb364dfcb6a821dd3abbf0c0257956b716b9691718ddfd453df4c`. The native fixture instead compiles against WPE's own v4 XML (SHA256 `0681c01199393662229b0d9f71a4bd502350ea8f782a7049fa30e392b50fb2c8`); v6 removes main_device and has a sampling-tranche contract not covered here.
- Reuses the foundation lane's `01-port-build-foundation/baseline-manifest.json` for the pinned Mesa release; that foundation is **RFC/held** and excludes the Mesa EGL paths from its Grate port. Neither WPE candidate depends on its unaccepted Grate C port; future integration against a settled foundation remains pending.

All source blobs, candidate before/after SHA256 values, patch SHA256 values and exact verification statuses are recorded in `work/grate-upstream-followups-20261103/07-wayland-format-feedback/evidence/source-manifest.json`.

## Candidate ordered patch series and files

1. `patches/0001-linux-dmabuf-create-feedback-object-for-surface-requ.patch` (SHA256 `b53236cf7e6a2c0ca4f536a4d33f4cb102af22160c82b36cded4a3ed8ee99646`), private commit `a00a7d6ff21e00ceb52955f71bfef160457e47fe`. WPE `src/linux-dmabuf/linux-dmabuf.cpp` only; function shares default/per-surface sender. **Duplicates upstream PR #208; held.**
2. `patches/0002-linux-dmabuf-gate-v4-on-valid-feedback-and-stop-lega.patch` (SHA256 `7096ff7e08a6f5ba05504c3863a8ace407c027965b47cfaabb5f4df5953c1ccb`), private commit `064f153dc3887d7b100b08574a7b5d46e3cc99d7`. WPE `src/linux-dmabuf/linux-dmabuf.cpp`, `src/linux-dmabuf/linux-dmabuf.h`, `src/ws-egl.cpp`. Requires patch 1 for the proposed series; allow version-3 fallback when table/device data cannot justify v4, and suppress forbidden v4 legacy events. RFC only: a genuinely empty EGL-supported-format set remains empty in v3, not fixed by this change.

Private source copy, staged source snapshots, generated native build directories and retained logs are all within this lane's work directory; no unrelated files are staged. `tests/strict-replay.sh` pins the WPE base commit, refuses pre-existing replay trees, applies both patches with `git apply --check --whitespace=error`, verifies resulting source hashes against both committed files, checks whitespace and proves a repeat application is rejected. Strict replay result **PASS**, no fuzz or already-applied skip.

## Protocol and surface classification

- v1–3 bind advertises supported legacy format/modifier events; v4–5 requests a default or per-surface feedback object (format_table, main_device, tranche target/flags/formats, tranche_done, done). For v4 the table alone does not advertise all entries: only tranche indices do. v6 adds sampling-tranche semantics.
- Main device / fd: useful to identify a candidate allocation device, **not** evidence of any supported format, modifier, row stride, import or EGL window config.
- EGL window: Mesa checks server-advertised format intersection and only sets `EGL_WINDOW_BIT` on supported native visuals; same-/different-GPU conversion paths need their own constraints.
- Pbuffer: Mesa may offer `EGL_PBUFFER_BIT` even with an empty Wayland window-format bitmap; separate surfaceless/device EGL does not use Wayland advertisement as its config source.
- Feedback after `wl_display_roundtrip`: a single roundtrip does not guarantee a future delayed update has delivered `done`. The mock's delayed case explicitly records `done_initial=0`, eventually `done=1`. This is a sequencing test, not an established Mesa defect.
- WPEBackend-fdo nested server: Cog outer Wayland EGLDisplay initializes WPEBackend-fdo's internal Wayland compositor; WebKit WebProcess connects via its own client socket. The nested server computes feedback from EGL format/modifier queries; it does not simply forward outer labwc's advertised formats.

## Executed commands and evidence

| Command (run from repository root) | Result / evidence | Scope |
| --- | --- | --- |
| `meson setup <lane>/build-wpe-stage1 <lane>/private-source/WPEBackend-fdo-stage1 --buildtype=debug && meson compile -C <lane>/build-wpe-stage1` | **PASS**, `evidence/meson-stage1-setup.log`, `evidence/meson-stage1-compile.log` | Native-host WPE patch 1 build |
| `meson setup <lane>/build-wpe-host <lane>/private-source/WPEBackend-fdo-1.16.1 --buildtype=debug && meson compile -C <lane>/build-wpe-host` | **PASS**, `evidence/meson-setup.log`, `evidence/meson-compile.log` | Native-host WPE patch 2 build |
| `<lane>/tests/strict-replay.sh` | **PASS**, `evidence/strict-replay.log` | Pinned WPE tag, exact two-patch replay |
| `python3 <lane>/tests/verify-wire.py` | **PASS 9/9**, `evidence/mock-wire.jsonl`, `evidence/mock-wire.stderr`, `evidence/wire-verification.log` | Real host Wayland client/server messages, **mock-only importer**; negative missing-surface case yields expected `invalid object` |
| `make test` | **PASS 199/199**, `evidence/make-test.log` | Existing SL101 Python host suite, **not** native Mesa C/ARM/GPU |
| `make check` | **PASS**, `evidence/make-check.log` | Existing SL101 Python compile check |

Mock scenarios: valid, empty, delayed, nonintersecting FourCC, nonintersecting modifier, different target/main GPU, mocked incompatible row pitch, successful per-surface feedback object lifecycle, and intentionally absent per-surface object that disconnects. The mock models 64-byte pitch rejection *solely as a fixture property*; this does not prove a hardware stride requirement or real kernel allocation support. The negative-case protocol error is expected regression evidence and its stderr was retained, not suppressed.

**Unexecuted:** target ARM cross-link, Mesa main native C test suite, WPE/EGL real integration tests, actual `gbm_bo_create*`, `eglExportDMABUFImageMESA`, DRM import/presentation, GPU pixels, runtime frame callbacks, physical device capture. No claims of full GLES2/GLES3 conformance, current renderer recovery or default promotion.

## Submission targets and next actions

1. **WPEBackend-fdo**: do not duplicate [PR #208](https://github.com/Igalia/WPEBackend-fdo/pull/208). Hold candidate patch 1 for review/coverage only. Patch 2 is an independent, host-buildable **RFC**, requiring production WPE protocol integration coverage, query-error/empty table tests, v1–v4 compatibility tests, feedback snapshot lifecycle and maintainer branch confirmation. Draft: `work/grate-upstream-followups-20261103/07-wayland-format-feedback/mr-draft-wpebackend-fdo.md`.
2. **Mesa**: no patch ready. If a real Mesa client parser/order bug is proven on pinned main, stage a standalone generic Mesa MR with source-native tests, never 0031. Held draft: `work/grate-upstream-followups-20261103/07-wayland-format-feedback/mr-draft-mesa-held.md`.
3. **Device qualification remains a separate supervised lane**: capture protocol bound versions, default and surface feedback including `done` across roundtrips, tranche indices and selected main/device, EGL window vs pbuffer choices, actual buffer-export format/modifier/pitch and server import result, first-frame callback and pixel oracle. Confirm both Cog/UI and WebProcess libraries before attributing the source. No hardware action occurred here.

No public MR/PR, message, push, deployment, desktop mutation, boot change or hardware run occurred in this lane. Final integration to the Grate foundation is **pending**, not inferred from this host evidence.
