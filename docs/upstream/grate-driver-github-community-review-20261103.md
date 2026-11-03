# Grate driver GitHub community review — 2026-11-03

- **OCP identity:** `SL101-LINUX-04-GRATE-DRIVER-GITHUB-REVIEW-20261103-72220B`
- **Review scope:** public Grate GitHub Mesa, Linux, libdrm; links to downstream history and maintainer statements.
- **Method:** GitHub issue/PR REST collections (open and closed), issue bodies and comments, branch and commit metadata, direct maintainer replies, official documentation. Date of inspection: 2026-11-03 (UTC).
- **Classification:** **VERIFIED** means directly observed in a linked source; **NOT FOUND** means not surfaced by the stated search/collection; **UNVERIFIED** means not independently reproduced or no authoritative source was accessible.
- **Local operation:** review/documentation only, with no device mutation or upstream publication.

## Executive conclusion

**VERIFIED:** The most relevant previous work is [Mesa issue #19](https://github.com/grate-driver/mesa/issues/19) (2026-10-08), reporting an **experimental Mesa 26.2.1 Grate port on Tegra30 Surface RT** that renders with **nested Wayland and native DRM labwc**. The author's changes include **64-byte linear texture-pitch alignment**, DMA-BUF import and CPU-access synchronization, premultiplied source-over blending/framebuffer fetch, scanout orientation, compiler fixes, and smaller stream uploads. The author explicitly limits these claims to a single device, without claiming full conformance or an upstream-ready patch. The [patch attachment](https://github.com/user-attachments/files/33225777/grate-surface-rt-48283c9.patch) is an upstream comparison candidate, **not** a verified SL101 fix.

**VERIFIED:** On 2026-10-09/10, [`digetx` first named `grate` as the GitHub target branch](https://github.com/grate-driver/mesa/issues/19#issuecomment-6084229719) but subsequently [recommended `libre-tegra/mesa` on Codeberg](https://github.com/grate-driver/mesa/issues/19#issuecomment-6084293622) and explicitly [said to try Codeberg first](https://github.com/grate-driver/mesa/issues/19#issuecomment-6097698620). The [Grate GitLab group](https://gitlab.com/grate-driver) is now archived/read-only and points to [Codeberg libre-tegra](https://codeberg.org/libre-tegra). The [GitHub organization](https://github.com/grate-driver) says development moved from GitHub to GitLab around mid-2023 and lists **`#tegra` on `irc.libera.chat`**.

**UNVERIFIED:** The `libre-tegra/mesa` Codeberg endpoint could not be independently inspected from this environment; a [2026-10-30 comment](https://github.com/grate-driver/mesa/issues/19#issuecomment-6519385071) reports a 404. Do not presume availability or identify a live maintainer branch without reconfirmation.

**NOT FOUND:** No GitHub Mesa issue or PR directly establishes a fix for Cog/WPE's **nested** Wayland server omitting `wl_drm.format`, `zwp_linux_dmabuf_v1.modifier`, or v4+ feedback format tranches. A repository search with `platform_wayland`, `browser`, and related terms did not establish such precedent. This is absence of evidence from the reviewed GitHub surface, not a claim that the problem has never been investigated elsewhere.

## Repository and branch activity (verified metadata)

| Repo | Default branch | Default branch HEAD / commit date | Repository `pushed_at` | Practical reading |
| --- | --- | --- | --- | --- |
| [grate-driver/mesa](https://github.com/grate-driver/mesa) | `grate` | [`5b013b9d`](https://github.com/grate-driver/mesa/commit/5b013b9d5c8affa177d4c1fcb868310852c43982), **2020-01-20** | **2022-12-19** | Default `grate` tree is historically old. Later `22.2.4` and other branches exist, but a push to another branch is not an update of `grate`. |
| [grate-driver/linux](https://github.com/grate-driver/linux) | `master` | [`33fad3cb`](https://github.com/grate-driver/linux/commit/33fad3cba453102214138ed957ea35cd94601abc), **2026-09-09** | **2026-09-09** | Recent GitHub patch acceptance, but much development also moved off GitHub. |
| [grate-driver/libdrm](https://github.com/grate-driver/libdrm) | `master` | [`3e3c53ed`](https://github.com/grate-driver/libdrm/commit/3e3c53ed85c30331a6c0ba2af349223654caa5dd), **2019-04-18** | **2022-02-05** | The default branch has not acquired a newer HEAD commit; later other-branch pushes do not imply current integration. |

All three were **unarchived on GitHub** when inspected. The activity dates are GitHub snapshots, not a general claim that driver development has stopped.

### Mesa — direct issue evidence

| GitHub item | Status / original date | Verified discussion and implication |
| --- | --- | --- |
| [#19: Mesa 26.2.1 Grate/labwc on Surface RT](https://github.com/grate-driver/mesa/issues/19) | Open, **2026-10-08**; last discussion **2026-10-30** | Single-device port claims working nested Wayland and DRM labwc, DMA-BUF synchronization, **64-byte** linear texture pitch, blending and scanout fixes. `digetx` recommends Codeberg first. Compare patches and test separately on Tegra20/SL101. |
| [#9: Wayland / Weston](https://github.com/grate-driver/mesa/issues/9) | Open, **2020-05-18** | Weston 3.0 logs include EGL 1.4, EGL DMA-BUF import/export extensions and **GLES2 / GL vendor Grate / renderer Tegra** before the reported failure. [`digetx` confirmed unsupported at that time](https://github.com/grate-driver/mesa/issues/9#issuecomment-630140758). An initialized EGL renderer was not proof of a working compositor; not evidence of this specific nested Cog format-negotiation failure. |
| [#13: How to contribute](https://github.com/grate-driver/mesa/issues/13) | Open, **2021-05-11**; last maintainer comment **2023-10-27** | [`kusma` identified fragment shader IR and texturing](https://github.com/grate-driver/mesa/issues/13#issuecomment-839572920) as major gaps in 2021. [`digetx` described command-stream capture and driver architecture](https://github.com/grate-driver/mesa/issues/13#issuecomment-841273599). In the 2023 reply, [`digetx` proposed rebasing onto recent Mesa first](https://github.com/grate-driver/mesa/issues/13#issuecomment-1782949811). This is historical guidance, not a 2026 conformance statement. |
| [#12: depthSize for TF101](https://github.com/grate-driver/mesa/issues/12) | Open, **2021-03-18** | Tegra20/TF101 user reported only 16-bit `depthSize` GLX visuals. [`kusma` described the fork as limited to glxgears](https://github.com/grate-driver/mesa/issues/12#issuecomment-802107813). Relevant to configuration capabilities, but **GLX depth size is not evidence of the Cog EGLConfig / Wayland format problem**. |
| [#15: Qt/QML support](https://github.com/grate-driver/mesa/issues/15) | Open, **2021-11-10** | Tegra30 Qt/QML user reported `drm_tegra_pushbuf_relocate() failed -22`, missing depth/stencil and crash, despite eglgears working. [`digetx` recommended software rendering](https://github.com/grate-driver/mesa/issues/15#issuecomment-965581178) for practical Qt workloads. |
| [#18: non-NEON llvmpipe](https://github.com/grate-driver/mesa/issues/18) | Open, **2022-12-26** | SIGILL on non-NEON hardware on fallback; [comment references Mesa MR 20766 as the fix](https://github.com/grate-driver/mesa/issues/18#issuecomment-1387205719). Relevant to SL101's ARMv7/no-NEON software fallback; not the DMA-BUF issue. |

Additional relevant build discussions: [#10](https://github.com/grate-driver/mesa/issues/10) (Meson/Ninja megadriver installation) and [#14](https://github.com/grate-driver/mesa/issues/14) (LLVM build failure), not evidence of a protocol bug.

**VERIFIED follow-up in #13:** [`digetx` explains](https://github.com/grate-driver/mesa/issues/13#issuecomment-839773777) that the special Grate libdrm compile dependency had been removed: driver-specific Tegra DRM handling moved into downstream drivers and a distribution's generic libdrm was sufficient for that Mesa generation. Check the concrete ABI for a new patch; don't infer that current Grate still requires the entire old libdrm fork.

### Mesa — direct PR evidence

The GitHub `pulls?state=all` collection returned **five PRs**, all closed, none open. At the inspected snapshot:

| PR | Outcome | Significance |
| --- | --- | --- |
| [#17: Grate 22.2](https://github.com/grate-driver/mesa/pull/17) | Closed **2022-12-17**, **unmerged** | Attempted Mesa 22.2.4 rebase; author reports unsupported shader parameters, broken glmark2 rendering and subsequent segmentation fault. Do **not** treat it as an accepted baseline. |
| [#5: missing include](https://github.com/grate-driver/mesa/pull/5) | Closed **2018-02-11**, unmerged | WIP build maintenance. |
| [#4: Sync with libdrm](https://github.com/grate-driver/mesa/pull/4) | Merged **2017-05-30** | Integration history / historical ABI coupling. |
| [#3: render targets + more](https://github.com/grate-driver/mesa/pull/3) | Merged **2017-05-24** | Early render-target work. |
| [#2: Misc fixes](https://github.com/grate-driver/mesa/pull/2) | Merged **2017-05-22** | Early cleanup. |

**NOT FOUND:** No GitHub Mesa PR addressing `platform_wayland.c`, nested WPE/Cog, or explicit EGLConfig format advertisement. This enumeration is confined to this GitHub repository; it does not cover Codeberg/other forks.

### Linux — kernel-side evidence

- **VERIFIED:** [Linux #136, rebase to 6.4-rc2+](https://github.com/grate-driver/linux/issues/136) (2023-05 to 2024-02) contains a substantive discussion among `digetx`, `kwizart` and `clamor-s` on kernel branch rebasing, shared patches, `drm/grate` history and device-specific branches. The [closing reply](https://github.com/grate-driver/linux/issues/136#issuecomment-1942387061) points to a partial/newer GitLab branch.
- **VERIFIED:** [Linux #141](https://github.com/grate-driver/linux/issues/141) and [merged PR #142](https://github.com/grate-driver/linux/pull/142) show a 2026-09-09 merge by `digetx` of a Surface audio codec fix. Graphics relevance is indirect; it establishes a **real recent acceptance path**, not a recent GPU-pitch fix. In [#141's maintainer response](https://github.com/grate-driver/linux/issues/141#issuecomment-5605665656), `digetx` says the custom Grate kernel is for WIP patches staged for upstream, and upstream Linux is normally preferred.
- **VERIFIED:** [Linux #91](https://github.com/grate-driver/linux/issues/91) documents TF101/Tegra20 EMC memory-controller **DT schema** warnings. These are *not* GPU texture-pitch constraints.
- **NOT FOUND:** In GitHub's reviewed open/closed issues, searches for `dmabuf` and `pitch` yielded no directly relevant Linux issue, and no documented kernel-side fix for Cog's omitted format advertisement. DMA-BUF protocol advertisement is normally a compositor/userspace concern; a kernel BO/import fault would need independent evidence.
- **External kernel documentation:** [drm/tegra kernel docs](https://dri.freedesktop.org/docs/drm/gpu/tegra.html) describe host1x, GR2D/GR3D on Tegra20/30, KMS and custom userspace ioctls. This is stronger evidence for kernel architecture than extrapolation from GitHub issue titles.

### libdrm — buffer and ioctl evidence

- [Issue #16](https://github.com/grate-driver/libdrm/issues/16), **open since 2017-06-26**: `digetx` asks whether mismatched imported BO flags in `bo_from_name` / `bo_from_dmabuf` should be forced with `drm_tegra_bo_set_flags` or rejected with `-EINVAL`; [follow-up](https://github.com/grate-driver/libdrm/issues/16#issuecomment-311204339) extends this to `drm_tegra_bo_wrap`. **This is import metadata semantics, not advertised Wayland formats.**
- [PR #26](https://github.com/grate-driver/libdrm/pull/26), **merged 2017-12-27**: avoids automatically disabling BO caching just because a BO is potentially exported as DMA-BUF/flink. Important BO-lifetime/caching precedent, but not a format-negotiation fix.
- [PR #17](https://github.com/grate-driver/libdrm/pull/17), **closed unmerged 2017-07-24**: flags-state/cache mismatch proposal. [PR #18](https://github.com/grate-driver/libdrm/pull/18), **merged 2017-07-24**, corrects BO creation/wrapping.
- [PR #43](https://github.com/grate-driver/libdrm/pull/43), **merged 2019-03-18**: BO cache optimization. Default-branch latest [2019-04-18 commit](https://github.com/grate-driver/libdrm/commit/3e3c53ed85c30331a6c0ba2af349223654caa5dd) extends caching.
- [Issue #45](https://github.com/grate-driver/libdrm/issues/45), **open since 2025-12-23** with no reply recorded at review time: `drmAvailable()` assumes `/dev/dri/card0`. This reflects issue activity, **not** renewed default-branch development.
- **NOT FOUND:** No recent reviewed libdrm PR on EGL/Wayland format negotiation, or directly relevant new tegra-specific ioctl patch. The historical libdrm fork must not automatically be assumed necessary for a current Grate Mesa port.

## Community engagement, venues and response times

**Verified, role-limited evidence (not a membership census):**

- **`digetx` / Dmitry Osipenko:** responds in Mesa [#19](https://github.com/grate-driver/mesa/issues/19#issuecomment-6084229719) on **2026-10-09** and merges kernel [#142](https://github.com/grate-driver/linux/pull/142) **2026-09-09**; presently the strongest verified contact in these GitHub threads.
- **`giuseppefava`:** posted Mesa [#19](https://github.com/grate-driver/mesa/issues/19) on **2026-10-08**, providing cross-device/cross-version research and a patch attachment; contributor, not established maintainer.
- **`kusma`:** substantial fragment shader/compiler discussion in [#13](https://github.com/grate-driver/mesa/issues/13) (2021) and early Mesa PRs; historically important, current availability unverified.
- **`kwizart` / Nicolas Chauvet:** [Mesa #17](https://github.com/grate-driver/mesa/pull/17) and [Linux #136](https://github.com/grate-driver/linux/issues/136) show Mesa/kernel rebase activity 2022-2024; present review bandwidth unverified.
- **`clamor-s`:** kernel/device branch discussions in [Linux #136](https://github.com/grate-driver/linux/issues/136), historically linked to Transformer support.
- **`zefr0g`:** 2026 author of merged [Linux #142](https://github.com/grate-driver/linux/pull/142); contributor, not necessarily repository maintainer.

**Observed first-response times, individual samples only** (GitHub issue creation to first substantive public comment, not an SLA):

| Discussion | First public response | Interval |
| --- | --- | --- |
| [Mesa #19](https://github.com/grate-driver/mesa/issues/19#issuecomment-6084229719): 2026-10-08 21:45:35 UTC | `digetx`, 2026-10-09 15:43:49 UTC | **17 h 58 min** |
| [Mesa #9](https://github.com/grate-driver/mesa/issues/9#issuecomment-630140758): 2020-05-18 10:51:47 UTC | `digetx`, 2020-05-18 12:12:37 UTC | **1 h 21 min** |
| [Mesa #13](https://github.com/grate-driver/mesa/issues/13#issuecomment-839572920): 2021-05-11 20:37:46 UTC | `kusma`, 2021-05-12 08:22:38 UTC | **11 h 45 min** |
| [libdrm #45](https://github.com/grate-driver/libdrm/issues/45): 2025-12-23 | none at inspection | **No response measured** |

**Suggested etiquette:** Open with `#tegra` on **irc.libera.chat** (explicitly listed by the [GitHub organization](https://github.com/grate-driver)), link the minimal reproducer and hardware/kernel/Mesa/firmware identity; then ask `digetx` / relevant libre-tegra maintainers which live repository and branch they want. The older [Grate wiki](https://github.com/grate-driver/grate/wiki/Grate-driver) describes build order and GL tests but is not proof of today's preferred patch destination. Generic Mesa EGL changes go through [upstream Mesa's contribution process](https://docs.mesa3d.org/submittingpatches.html) rather than automatically through the Grate fork. Do not send duplicate PRs to multiple forks without agreement.

## Prior Wayland work versus the SL101 problem

| Environment | Evidence | What is established / not established |
| --- | --- | --- |
| **Tegra20 Weston 3.0 (2020)** | [Mesa #9](https://github.com/grate-driver/mesa/issues/9) | EGL 1.4 / GLES2 Grate initialized, but Weston failed and maintainer said unsupported. **Not** a positive Wayland validation. |
| **Tegra30 Surface RT, Mesa 26.2.1 port (Oct 2026)** | [Mesa #19](https://github.com/grate-driver/mesa/issues/19) | Contributor reports correct native DRM and nested labwc, including transparency/window decoration and cursor. Hardware-specific report; no validated browser/conformance claim. |
| **Tegra20 SL101, labwc + nested Cog/WPE** | Local [WPE investigation](../sl101-wpe-fdo-egl-investigation-20261103.md), [Wayland format investigation](../sl101-grate-wayland-format-bypass-20261103.md), [upstream submission split](grate-mesa-submission-split-20261103.md) | Local observations are not public Grate upstream precedent. The generic format-bitmap bypass is **not** a proven safe upstream fix: a render node alone does not guarantee supported format/modifier import, and an early display query may target a not-yet-initialized EGLDisplay. |

**Critical distinction:** format/pitch layout issues (`drm_tegra_bo_*`, texture sampler pitch, DMA-BUF synchronization) are different layers from Wayland protocol feedback and Mesa EGLConfig filtering. A Mesa EGL format-filter bypass is not justified merely because Grate can produce a format; the **compositor must accept/import it**. Separate the outer labwc server from WPEBackend-fdo's internal server, and verify whether the failure is an absent advertisement, premature query, wrong display, delayed feedback, unsupported modifier, or a distinct buffer allocation error.

## Recommended upstream preparation order

1. **Coordinate, do not duplicate:** read [#19](https://github.com/grate-driver/mesa/issues/19), compare its attached patch against the SL101 patches, and ask in `#tegra` where the active libre-tegra Mesa tree is now hosted, especially given the 2026-10-30 Codeberg 404 report.
2. **Keep versioned diff evidence:** pin the exact Mesa source/branch SHA and Grate driver integration ABI; distinguish GitHub `grate` (2020 HEAD), `22.2.4` (2022 branch), the experimental Mesa 26.2.1 port, and the SL101 Mesa 25.0.7 overlay. Do not call `grate` a current Mesa release.
3. **Build a minimal nested Wayland reproducer:** record `wl_registry` globals/versions; `wl_drm.format`; dmabuf modifier events or v4+ feedback format table, main device and tranche events; EGL display initialization order; selected EGLConfig visual; chosen DRM format, modifier, producer device and actual buffer import/presentation.
4. **Qualify pitch separately:** assert CPU memory strides, imported DMA-BUF attributes and sampled GPU pixels across a width set discriminating 16/32/64-byte alignment. Compare against [#19's 64-byte observation](https://github.com/grate-driver/mesa/issues/19), but don't apply a blanket rule without per-format/layout evidence on Tegra20. See [local pitch investigation](../sl101-grate-texsubimage-pitch-alignment-20261103.md).
5. **Split patch ownership:** Grate Gallium driver and winsys → agreed active Grate/libre-tegra tree; generic EGL/DRI2 state handling → upstream Mesa if reproducible on current main; libdrm BO import/export semantics → corresponding libdrm owner; Wayland dmabuf-advertisement defect → WPEBackend-fdo/Cog if demonstrated there. Hardware deployment wrappers remain in SL101 repository.
6. **Submit tests and safety evidence:** GLES2 API/correct-pixel coverage, ARGB/XRGB premultiplied alpha, partial-damage and scissor, padded-pitch/row-length oracle, DMA-BUF attach/import errors, synchronization and BO lifetime tests, plus known-good software-rendered recovery. GPU initialization by itself is not visual or conformance acceptance.

## Documented uncertainty / limitations

- GitHub issue and PR snapshots cover the **named GitHub repositories**. They do not provide an exhaustive Codeberg/GitLab/IRC archive search. `libre-tegra` Codeberg endpoints could not be independently inspected from this environment.
- Keyword search is not equivalent to proving no bug exists. Exact `dmabuf` searches can miss hyphenated `DMA-BUF`; the issue/PR enumeration and manual body review matter more than counts.
- The `grate-driver/mesa` default branch `grate` was explicitly selected in Oct 2026, but its commit is dated **2020**, not 2026. `pushed_at` is repository-wide, not branch-specific.
- No original experimental Surface RT patch was built or executed on the SL101 for this review. No independent source confirms browser rendering, GLES2 conformance, or production-stable native Wayland on the SL101.
- The OCP task lookup through the `sl101_linux` workspace reports a **different project ownership identity** for this task. This report is filed at the requested repository root without inventing a second packet or transitioning OCP state.

## Source directory

- [Grate GitHub organization](https://github.com/grate-driver) — historical move to GitLab, Libera `#tegra`.
- [Archived Grate GitLab group](https://gitlab.com/grate-driver) — explicit migration to Codeberg `libre-tegra`.
- [Grate Mesa issues](https://github.com/grate-driver/mesa/issues?q=is%3Aissue) / [PRs](https://github.com/grate-driver/mesa/pulls?q=is%3Apr).
- [Grate Linux issues](https://github.com/grate-driver/linux/issues?q=is%3Aissue) / [PRs](https://github.com/grate-driver/linux/pulls?q=is%3Apr).
- [Grate libdrm issues](https://github.com/grate-driver/libdrm/issues?q=is%3Aissue) / [PRs](https://github.com/grate-driver/libdrm/pulls?q=is%3Apr).
- [Grate driver wiki](https://github.com/grate-driver/grate/wiki/Grate-driver) — historical build advice, not current repository authority.
- [Linux drm/tegra docs](https://dri.freedesktop.org/docs/drm/gpu/tegra.html).
- [NVIDIA public Tegra application notes](https://download.nvidia.com/tegra-public-appnotes/index.html), [NVIDIA hardware/TRM portal](https://developer.nvidia.com/tegra-hardware-sales-inquiries-0) and [NVIDIA developer downloads](https://developer.nvidia.com/embedded/downloads) (Tegra 2 TRM listed).
- [Mesa patch submission guide](https://docs.mesa3d.org/submittingpatches.html).
