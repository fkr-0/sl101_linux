# SL101 release-consolidation design: from working prototype to reproducible Nura system

**Status:** Proposed design, 2026-11-06. **Repository:** sl101_linux. **Trigger:** execute the release work only after a separately recorded stable-runtime qualification. This document does not assert that such a gate has passed, authorize flashing, or replace a live graphics owner.

## 0. Executive decision

Treat the SL101 effort as **four independently versioned products**, rather than one ever-growing Mesa patch pile:

1. **Device/boot distribution:** Nura/postmarketOS-compatible armv7/musl system image, 7.x kernel/DTB/modules, configuration, rollback and first-boot policy.
2. **Graphics stack:** Grate Mesa + compatible libdrm-tegra + kernel interfaces, with a truthful GLES2 capability boundary and a separate optional glibc browser build.
3. **Desktop/application layer:** Sway/wlroots, foot, NuraLoumi, input/audio/network services, and a recoverable Pixman alternative.
4. **Optional browser/media layer:** isolated Cog/WPE and VDE tooling with distinct ABI, sandbox, modifier and video-quality gates.

**The target is not merely “it boots”.** Release acceptance is: a clean source checkout builds the same functional artifacts without an inherited ignored work tree; a U-Boot-capable SL101 can boot a newly created MicroSD image with one *host-side* build command; its default desktop has proven pixels, input and rollback; optional browser/media capabilities are truthfully labeled. No automatic destructive eMMC flash is part of “one step”.

The strategy is **one curated downstream release first; several small, reviewable upstream contributions second**. Rebase these two deliverables from the same reviewed source and evidence, but do not make upstream acceptance a prerequisite for a reproducible SL101 image.

## 1. Achievements and evidence boundaries

The following is a categorized inventory, **not** a blanket feature-completeness claim. Earlier reports describe different kernels, deployed binaries and source states; date, ELF hash and test route always qualify a result.

| Domain | What the project has achieved | Evidence / limitation |
| --- | --- | --- |
| Boot and board support | SL101 APX/Fusée → RAM U-Boot → MicroSD extlinux/Linux path; guarded kernel/DTB raw-slot tooling; EC/keyboard and Wi-Fi bring-up; coherent 7.0.1-postmarketos-grate kernel/config/DTB/modules | docs/boot-fusee-uboot/README.md; docs/sl101-kernel7-consolidation.md; docs/sl101-rawboot.md. U-Boot in RAM versus permanently installed U-Boot **must not** be conflated. |
| Nura root filesystem | pmbootstrap/pmaports Nura image and private flashable SD snapshot, OpenRC, services, kernel handoff/failback prototypes | docs/sl101-nura-bringup.md; docs/sl101-nura-flashable.md; docs/sl101-kernel7-persistent-staging.md. A private copied rootfs is not a reproducible public clean build and contains device secrets. |
| Low-level GPU | Actual Tegra20 GR2D/GR3D pixels; Mesa 25.0.7 Grate Gallium port; shader opcode, row-lifetime, texture/layout, state, fences, EGL and GBM work; bounded on-chip pixel oracles | docs/sl101-grate-production-20261004.md; docs/sl101-fp-bank-lifetime-dossier-20261106.md; docs/sl101-patch-atlas-20261106.md. Partial support and explicit rejection are deliberate; not GLES2 conformance. |
| Display/compositing | Earlier real-display labwc Grate pixel qualification, scanout orientation and private wlroots exact-1:1 filtering fix; later native Sway 1.12 + GLES2/Grate loaded successfully, green swaybg, foot/NuraLoumi panel and i3-style bindings | docs/sl101-grate-production-20261004.md; docs/sl101-musl-sway-green-20261106.md; docs/sl101-sway-i3-config-parity-20261106.md. Process maps/EGL are **not** current all-pixel proof; source-level Sway patch has not been shown necessary. |
| Dual-ABI builds | ARMHF glibc integrated Grate and ARMHF musl integrated Grate plus EGL wrapper, with identical 17-file source manifest; separate isolated package/payload work | docs/sl101-integrated-0044-qualification-20261106.md. Host QA passed, **0044 not deployed or device qualified**. Native 0044 reused old Mesa core archives, so is **not** full clean rebuild. |
| Browsers | Debian armhf Cog/WPE and Firefox routes, Cog KMS and nested Wayland tests, EGL format-negotiation diagnosis, WebKit shader/pixel instrumentation | docs/sl101-browser-assessment.md; docs/mesa-investigation-results/SYNTHESIS.md; docs/sl101-cog-gpu-qualification-20261103.md. WPE 2.54 Skia is not proven GPU-accelerated on Grate. No blanket “browser works correctly” gate. |
| Media | Tegra VDE H.264 decode and a bounded direct KMS zero-copy display route; transcode, playback, GStreamer and audio diagnostic tooling | docs/sl101-video-playback.md; docs/sl101-video-sway-musl-20261106.md. The **2026-11-06 Sway video route fails pixel qualification**: Wayland DMA_DRM negotiation fails; I420→RGBx reaches EOS but produces visible corruption; software control has A/V issues. |
| Interaction/operations | Touch/slider keyboard/keyd/VT recovery, WM8903 ALSA mitigation, PipeWire and WayVNC services, session/renderer switch, constrained SSH deploy and rollback, input simulation and bounded captures | docs/sl101-device-config/DEPLOY.md; docs/sl101-audio-pipewire/README.md; docs/sl101-remote-control.md. Some mirrored files/configs are under active concurrent change. |
| Engineering discipline | Patch provenance atlas, source-hash replay, unit fixtures, hardware pixel matrix probes, rollback receipts, migration to canonical sl101_linux ownership | docs/sl101-patch-atlas-20261106.md; docs/MIGRATION-20261003.md; tests/. Integrated 0044 checkpoint: **592 host tests passed, one skipped; make check passed**; no automatic device promotion. |

**Most important current contradiction to preserve:** the older Sway-compatible musl Grate library was actually mapped by the live Sway process, but the new **0044** compiler-integrated musl/glibc candidates were only built/staged on the host at the latest qualification. Do not merge those statements into a fictitious “0044 Sway/browser/video success”.

### Source authority: do not promote historical experiments by accident

- The **49-patch inventory** and its machine JSON atlas are a history/index, not a valid ordered release series. Some patches are malformed, duplicate-numbered (0004/0012/0038), superseded (0043 → 0044) or explicitly HOLD (Cog teardown UAF, importer/resource-export validation).
- The currently preferred integrated Mesa source is the **17-file SHA-guarded 0044 overlay** in ignored work/sl101-full-integration-20261106/, not a fresh sequence of patch -p1 on the legacy series. Its source manifest is separately pinned in docs/sl101-patch-atlas-20261106.md.
- Ignored work/ and tmp/ artifacts are evidence and build dependencies of historical attempts, **not a distributable source package**.
- Any final release candidate needs a new named Git revision or signed source archive, exact patch list and hashes, full clean rebuild and hardware attestation.

## 2. Target architecture and provenance

~~~text
                         PINNED INPUTS (no moving HEAD)
  U-Boot / boot contract   Nura pmaports   Linux 7.x   Mesa 25.x + Grate
  libdrm-tegra             wlroots/Sway    NuraLoumi   Cog/WPE optional
                  \          |                 /
               source.lock + vendor licenses + patches
                               |
                 isolated armv7 no-NEON builders
                      /                    \
           native musl packages        glibc browser bundle
             (.apk packages)            (optional, isolated)
                      \                    /
                 image compositor + package manifest
                               |
                   versioned MicroSD image
                 + hash + SBOM + firstboot config
                               |
             physical SD / U-Boot / boot qualification
                               |
               verified Sway/GLES2/Grate + Pixman fallback
                               |
          optional Cog, VDE and extended browser/media qualification
~~~

**Hard invariants**

1. Pin every source commit/tarball digest, submodule, patch blob, toolchain image digest, sysroot and package-lock input. Record both source-tree hash and output hash. Network access may populate a verified cache; an offline rebuild must work from that cache.
2. Never combine glibc and musl ELF directories or install private experimental libraries over system libraries. The libdrm-tegra ABI and dynamic loader closure must match each runtime.
3. Compile for Tegra20 **ARMv7/VFPv3-D16 without assuming NEON**. Audit ELF architecture/attributes/instruction paths and test the non-NEON execution route; do not reject intentionally CPU-dispatched NEON code solely because its bytes exist in an ELF.
4. Do not claim acceleration from EGL initialization, environment labels, mapped library alone, successful app exit, VDE decode alone or visual impressions. Demand independent reference pixels, relevant DRM/Wayland transfer proof, active ELF hash, timing and fault deltas.
5. Preserve a selectable Pixman session/VT rescue and a known-good boot medium. Build, flash, boot and graphics default promotion are **separate permissions**. Only one authorized operator owns live DRM/session mutation.
6. NuraLoumi implementation stays in its own Git repository. SL101 keeps the packaging overlay, target policy and device acceptance, not a copied divergent app source.
7. A new install must not clone another tablet’s SSH private keys, Wi-Fi secrets, machine ID or other per-device state.

## 3. Workstream A — clean U-Boot-to-desktop reproducibility (highest priority)

### A1. Freeze a canonical release source set

Introduce a **tracked** release manifest (suggested release/sl101.lock.yaml or release/manifest.json) containing:

- project and artifact version; pinned Nura/pmaports/pmbootstrap, Linux, SL101 DTB, firmware, U-Boot config, Mesa/Grate/libdrm, wlroots/Sway, NuraLoumi, optional Cog/WebKit;
- provenance URL/commit/tag/archive SHA256, license, local patches in **unambiguous order**, preimage/postimage SHA256 and expected source tree digest;
- builder OCI image **digest**, Meson/CMake/abuild versions and exact target compiler flags; armv7 sysroot/musl ABI plus separate glibc ABI;
- package names/versions/dep graph, shared-object SONAME/DT_NEEDED closure, entrypoint/unit filenames, image partition layout, artifact checksums;
- accepted vs optional/held patch dispositions, test gates and known limitations.

Convert the 0044 ignored source overlay into either (a) a reviewed **tracked Git patch series based on a pristine pinned Mesa archive**, or (b) a separately pinned, content-addressed **Grate integration Git tree**. Prefer a Git tree with replayable commits for upstream work; keep original raw patch/index and frozen hashes as historical evidence. Do not copy binary output trees into Git. Ensure a fresh checkout alone plus publicly fetchable/pinned sources can reconstruct the *entire* tree and **every** linked object. A build that borrows old native core archives is an intermediate artifact, not A1 completion.

### A2. One host command creates the bootable image

Define a future CLI with two explicit profiles:

~~~sh
# DESIGN CONTRACT; commands are proposed, NOT implemented yet.
./tools/sl101-release build --profile nura-sway-grate --lock release/sl101.lock.yaml --out dist/
./tools/sl101-release verify --image dist/sl101-nura-sway-grate.img
# Optional, separately versioned:
./tools/sl101-release build --profile browser-glibc-overlay --lock release/sl101.lock.yaml --out dist/
~~~

Build pipeline should: fetch+hash lock inputs → materialize pristine trees → strict source replay → deterministic no-NEON cross-build → build local signed Alpine/Nura .apk packages → assemble rootfs via Nura/pmbootstrap/image tooling → install matching kernel/DTB/modules/firmware → configure OpenRC/seatd/Sway/Pixman rescue → emit MicroSD extlinux boot files/partitions and image manifests → run structural checks. Use a containerized/pinned SDK, rootless source build where possible, and small controlled privileged image-assembly step. Do not import mutable system state from the current tablet.

Build profiles are **not** a product-variant explosion: the default is native musl and Sway; glibc Cog is an optional separately testable payload; rescue/Pixman is installed as a fallback rather than a separately maintained OS fork.

### A3. “Empty tablet with U-Boot” is one image, not a blind eMMC rewrite

Supported v1 entrypoint: **already-bootable U-Boot (persistent or loaded through the established APX route) + removable MicroSD**. First identify the boot model, then U-Boot boots the image’s known extlinux/kernel+DTB/root UUID contract. Do not assume the earlier internal 6.18 + rootbind path is the same as MicroSD extlinux. Preserve the APX volatile loading documentation and the original bootloader rescue path.

~~~sh
# DESIGN CONTRACT; require an explicit verified removable-device target.
./tools/sl101-release flash --image dist/sl101-nura-sway-grate.img \
  --target /dev/VERIFIED_REMOVABLE_SD --dry-run
# A second, interactive, confirmation-token-gated invocation is required to write.
~~~

Make first boot generate unique SSH host keys/machine ID, provision network separately and expose an **offline local-console** setup if network absent. Default should not auto-run experimental suspend, eMMC flash or dangerous recovery commands. Keep immutable software origin distinct from user data and per-device secrets. A verified recovery card is mandatory for device release testing.

**Acceptance A:** independent clean checkout on a second host; cache-backed offline rebuild of **full Mesa/wlroots**, not partial relink; deterministic input/output manifests (byte-identical where feasible, otherwise documented reproducible differences); no hidden work/ dependency; SD image passes partition/DTB/module/rootfs integrity checks; human-supervised cold boot, login, input corners, Wi-Fi/SSH, audio, graphics pixels, and A/B rollback all PASS.

## 4. Workstream B — consolidate Grate, Mesa, libdrm and kernel interfaces

### B1. Replace “collection of fixes” with a maintainable driver branch

First decide and pin the **real maintainer base**. The old grate-driver/mesa GitHub default branch is historically a 2020 fork; 2026 maintainer comments in issue #19 directed contributors toward **libre-tegra/mesa on Codeberg**. Codeberg access/current canonical branch is **unverified** here and must be confirmed with maintainers. Do not target that URL blindly or assume that historical GitHub permissions imply an active review venue.

Maintain one downstream clean branch containing the released implementation, **then submit multiple dependent but individually reviewable change sets**. Suggested Grate/libre-tegra split:

| Series | Subject and tests | Upstream disposition |
| --- | --- | --- |
| G0 / foundation | Meson/loader/winsys/Mesa-25 port, exact libdrm ABI, basic GR3D smoke | Initial architectural discussion/port PR; prerequisite for most later changes. |
| G1 / shader semantics | FP/VP arithmetic, CSEL/LRP/DP2/DP3/DP4, SFU, valid NIR lowering, TEX coordinate materialization, discard; 0044 row/scalar lifetimes and explicit capacity rejection | Split shader correctness and row-lifetime commits; tiny independently checked TGSI/NIR-to-pixel fixtures. 0043 is obsolete. |
| G2 / resources | A8/L8/LA8/BGRA formats, sampler views, per-level pitch 64 vs older 16 assumptions, mip/mirror, import/export, modifier/stride/top-down handling | Matrix of format×usage×width×pitch×import; reject unsupported allocation instead of advertising more caps. |
| G3 / state/draw | Blend variants, selective depth/stencil clear, bounded stencil ops, large draw splitting, multidraw/index validation, atomic preflight | Commit boundaries follow observable feature+negative tests. No claim of full GLES2 until FS uniforms/dynamic flow/cube/etc. are genuinely solved. |
| G4 / sync/lifetime | BO/fence ownership, end-of-frame drains, multi-context/GR3D serialization and error teardown | Require no unbounded waits, no use-after-free, completed GPU jobs before cross-process release; consider kernel-level ownership where appropriate. |
| G5 / driver QA | Piglit/deqp subsets, reference pixel fixtures, supported-vs-rejected caps, performance counters and fault sampling | Test assets can follow their own small PR; link results per hardware revision. |

**HOLD** malformed 0029/0033/0034, the unrelated historical inverse delta, superseded 0043, the Cog teardown patch with ASan reentrant UAF, and external DMA-BUF importer/resource-export candidates until dedicated proof. The release branch should contain corrected code only—not every existing patch filename. Reconcile duplicate numeric names with stable semantic IDs and a machine-checked ordered manifest.

### B2. Separate upstream destinations by ownership

- **Mesa main (freedesktop GitLab MRs):** generic EGL platform behavior only. The 0001 NULL-guard currently does not propagate failure correctly; the 0031 empty-format-bitmap bypass can accept unusable formats. Reproduce current-main, use Wayland protocol feedback traces, define correct error/cleanup semantics, and submit **two separate generic MRs only if still needed**. Neither current patch should be sent unchanged.
- **Grate/libre-tegra driver fork:** Grate Gallium/GBM/winsys, Grate-specific Mesa integration, shader, resources and state series (G0–G5), against the maintainer-agreed base; not a giant mixed EGL+browser+device PR.
- **libdrm-tegra:** importer list initialization and DMA-BUF import validation belong in a **separate libdrm PR**, with syscall and invalid-fd/error-path tests. Ensure its actual upstream/review venue and ABI contract.
- **Kernel/DTB/EC:** only generic board/kernel improvements to the relevant kernel/Linux/pmaports maintainers, with regression tests and maintainership confirmation. SL101 deployment layout and private boot tooling stay local.
- **Cog/WPE:** distinct platform/format negotiation, input and teardown proposals when verified; no driver patches in Cog PRs. The unsafe teardown candidate is not releasable.

**Upstream acceptance gate:** fixed base/tag; one logical change per commit (buildable after each relevant commit); test and failure reproducer; exact Tegra20 evidence, issue link, current API review, license/sign-off, clean CI; request maintainer preference before opening a long dependent series. It is better to file **several focused PRs/MRs** than one broad patch bomb. A foundation proposal may be one architectural RFC; implementation lands as stacks/subseries after agreement.

Relevant local prior review: docs/upstream/grate-mesa-submission-split-20261103.md; docs/upstream/grate-driver-github-community-review-20261103.md. Official external guides: https://docs.mesa3d.org/submittingpatches.html and https://github.com/grate-driver/mesa/issues/19.

## 5. Workstream C — Sway hotfix and desktop default

Distinguish three things often collectively called a “Sway fix”:

1. **Sway itself:** 1.12 was observed launching and rendering through private musl Grate/GLES2 without a demonstrated Sway source patch. Therefore **do not create a fictional Sway upstream patch**.
2. **wlroots exact-1:1 patch:** the earlier verified labwc stack used a private wlroots 0.20.2 GLES2 filter optimization (docs/sl101-wlroots-exact-1to1.patch). Rebuild pristine wlroots vs patched wlroots on the *same* pinned Mesa/libdrm and compare pixel/format/rotation/scaling/damage/oracle results; drop it if no longer necessary. If a general bug remains, write an isolated wlroots upstream regression and negotiate a small MR with an appropriately scoped conditional.
3. **SL101 compositor policy:** OpenRC sl101-desktop service, renderer env, Sway bindings, seatd, output transform, foot/tmux launcher, NuraLoumi panel, WayVNC, keyd VT rescue and the Sway green-background test. These are **device package configuration**, not Sway upstream code.

Use a single declarative config source. Mirror device-side config to the repository only after reviewing current actual hashes; eliminate duplicate labwc-vs-Sway launcher logic by a supported compositor variable and validated profiles. Select Sway+Grate only when a *pixel-qualified* build is chosen. Retain a one-command/operator-controlled Pixman recovery path and boot-safe rescue policy. No fallback that silently runs software under a GPU badge; show renderer backend *and mapped Gallium/libdrm SHA* from reliable diagnostics. The “Unknown” NuraLoumi panel label is a compositor-process detection bug, not proof of Pixman; repair in the separate NuraLoumi provider repository and test on both labwc/Sway.

**Acceptance C:** restart + three cold boots, Sway IPC/config match, touch geometry and keyboard/VT escape, tiling/floating, output/cursor/scaling/damage, no hidden system-library replacement, stable 30-minute interaction soak, renderer label accurate, rollback repeatable. Do not assume the video path succeeds because the desktop passes.

## 6. Workstream D — Nura packages and optional applications

Here **APK means Alpine/Nura Linux package (.apk built from an APKBUILD), not an Android APK**.

Package in dependency order, using a host/pmbootstrap clean-build environment and signed local repository:

- **nura-grate-libdrm** (or an ABI-namespaced libdrm-tegra build, if the system libdrm is incompatible), **nura-grate-mesa** with explicit EGL/GLES/GBM/DRI runtime library closure. Keep mutually incompatible native/glibc layouts separate; default .apk is musl only.
- **nura-sl101-session**: OpenRC service, Sway/labwc rescue, foot, keyd mappings, WM8903 audio setup, WayVNC policy and system defaults. Config files should support upgrades without replacing user overrides.
- **nuraloumi**: compiled directly from pinned /home/user/code/nuraloumi commit into multiple native armv7/musl APK subpackages if useful (panel, controls/ctl, assets/config). Do not vendor/duplicate its source here. Ensure Rust target/sysroot, no-NEON, protocols and compositor backend detection.
- **nura-sl101-browser** optional: URL launcher/config + separately pinned Cog/WPE glibc chroot/bundle **only if qualified**; do not treat it as an Alpine-native APK merely because a wrapper is packaged.
- **nura-sl101-media** optional: tested VDE player/transcode interface with clearly labeled KMS-exclusive versus Wayland paths. The current corrupt Sway-video path must remain opt-in/diagnostic until fixed.

First supply private versioned .apk builds. Once the clean build works, propose an SL101 device package/overlay to the actual Nura/pmaports maintainers as appropriate. A downstream packaging overlay may be necessary for experimental Grate while retaining upstream package-name/ABI hygiene. Capture license, package provenance, upgrade/uninstall and downgrade behavior. No post-install script may silently flash eMMC, restart an active compositor, or enable unqualified services.

**Acceptance D:** abuild/pmbootstrap compile from locked sources, local signed repo install and remove on a disposable rootfs, files owned by correct package, no overwritten system Mesa, no unresolved DT_NEEDED, correct native binary architecture; first-boot panel + services start from packaged binaries with no custom /opt install or ignored host source tree.

## 7. Workstream E — documentation, Git history and repository hygiene

Current snapshot (2026-11-06): main at 956b5e8; **11 modified tracked paths**, **no staged paths**, and an untracked/generated tree with **more than 11,000 entries** (mostly build/). Exact counts may change while other workers run. The ignored work/ and tmp/ are not automatically safe to delete: they contain one-of-a-kind sources, build recipes and raw hardware evidence.

**Do not run git add -A, git clean -fdx, or mass-commit all experimental artifacts.** Use an explicit source/data retention classification, owner claims and independent diff review:

| Class | Action |
| --- | --- |
| Canonical source/release | Track minimal scripts, pmaports/APKBUILD recipes, source lock, patches/tests, deterministic build entrypoint, service config, recovery tooling, docs. |
| Historical but valuable | Retain dated docs, old patch atlas and negative evidence; move to a clearly linked archive only with intact provenance, not destructive rewriting. |
| Generated/recoverable | Build objects, Mesa extracted trees, chroots, toolchain caches, temporary framebuffer captures: ignore outside Git; optionally hash/upload to versioned artifact storage. |
| Sensitive/device-specific | Wi-Fi credentials, SSH material, BCT/SBK, boot-slot images, real tablet backups: private encrypted storage, never Git or public image. |
| Awaiting adjudication | Untracked source candidates, modified patch series, duplicate tests, compositor files: assign reviewer and provenance; split logically, preserve unmerged workers. |
| Documentation | A concise current README and installation guide, supported/unsupported features, diagnostics, fallback, release notes, patch-status matrix, upstream contribution map. |

Recommended layout (**future**, not an instruction to move files while active claims exist):

~~~text
release/
  sl101.lock.yaml              # immutable inputs + target matrix
  profiles/                    # baseline, browser option, diagnostic profile
packaging/
  pmaports/                    # device and nura-sl101 packages
  apk/                         # Mesa/libdrm/session/NuraLoumi APKBUILDs
patches/
  mesa-grate/                  # unique series IDs + tests
  libdrm-tegra/
  wlroots/                     # only if retained
  cog/                         # only reviewed patches
tools/sl101-release/           # fetch, replay, build, image, verify, guarded flash
tests/
  host/
  hardware/                    # captures/oracles, not private raw device data
docs/
  install-uboot-microsd.md
  architecture.md
  graphics-support-matrix.md
  recovery.md
  upstream.md
  archive/                     # historical evidence index, preserve links
dist/                          # ignored output, manifests retained separately
~~~

Practical Git commit progression after freeze: (1) source lock and provenance; (2) curated build/patch replay; (3) clean musl packages and image tooling; (4) desktop/Sway and NuraLoumi integration; (5) optional browser/media; (6) tests/gates; (7) README/recovery/upstream docs. Each commit or small series passes host checks and has explicit ownership/reviewer evidence; avoid mixing unrelated dirty state. Save a release tag only after independent fresh image validation. Push/public publication is a separate approval.

## 8. Qualification ladder and release criteria

| Gate | Required oracle | Promotion result |
| --- | --- | --- |
| R0 — freeze | Exact source and artifact hash, ownership, current patches/holds, no lost dirty changes | Candidate named, NOT released |
| R1 — clean build | Fresh checkout + pinned/offline source/cache; full Mesa/wlroots/Alpine .apk builds; ELF/ABI/symbol/dependency audit | Host-build reproducible |
| R2 — image | U-Boot extlinux/root UUID, partitions, 7.x kernel+DTB+all modules/firmware coherent, firstboot secrets, package inventory | Bootable image candidate |
| R3 — physical desktop | Exact live library SHA, GPU pixel matrix (incl. 0044 cross-EXEC, FIXED10 negatives, blend variants), 1280×800, formats/stride, rotated buffers, input/VT/seat, fault delta, 30-min interaction, cold boot ×3 | Default Sway+Grate eligible |
| R4 — browser | KMS-Cog and Sway-Cog **separately**; no software fallback masquerading as GPU; real frame/image oracles, WebKit process/sandbox, memory/fences/input | Optional browser package eligible |
| R5 — media | VDE decode **and** correct presented frames, DMA-BUF modifier compatibility or verified conversion, A/V sync/drop rate, stop/restart recovery | Video packaging eligible |
| R6 — release | Release notes, SBOM/license, public source reproducibility instructions, restore/reflash proof, independent review, no known P0 regressions | Sign/tag/publish only on explicit approval |

The **first stable runtime** that triggers this work may have unresolved R4/R5; do not silently widen the release definition. A desktop-first release can explicitly ship browser/media as experimental or omit them. Conversely, 0044 source integration passing host gates is not enough to mark R3.

## 9. Sequenced implementation plan (after stable-runtime trigger)

| Order | Priority | Deliverable / owner boundary | Dependency and exit |
| --- | --- | --- | --- |
| 0. Freeze the winner | P0 | One root operator records exact running kernel, Mesa/libdrm/wlroots/Sway hashes, all local patches, screen/AV oracle, recovery procedure | Current experiment completes and rollback works; no concurrent live graphics mutation. |
| 1. Evidence/repository audit | P0 | Release engineer + independent reviewer reconcile 17-file overlay, patch atlas, in-flight claims, staged/dirty files; classify all input artifacts | R0: no unowned changes or ignored-only release dependency. |
| 2. Build foundation | P0 | Build engineer creates pinned source lock, private replay, full clean glibc/musl build and reproducible toolchain images | R1: fresh-host CI/artifact gates pass, no borrowed core archives. |
| 3. Native packages | P0 | Packaging engineer creates libdrm/Mesa, session and NuraLoumi APKBUILDs, test local repo and upgrades | Installed closure works in disposable rootfs. |
| 4. SD image + boot | P0 | Boot/package owner creates single-command MicroSD image and guarded writer; root owns physical boot tests | R2 → R3 on clean SD, no eMMC assumption. |
| 5. Sway policy/hotfix | P1 | Desktop owner compares pristine/patched wlroots and consolidates OpenRC/config; NuraLoumi owner fixes label | R3 with correct-pixel/rollback and keyd escape. |
| 6. Upstream prep | P1 | Port maintainer contacts Grate/libre-tegra, separates 5–6 series and generic Mesa EGL MRs, distinct libdrm proposal | Maintainer-agreed bases, clean branch+tests, no unreviewed public submission. |
| 7. Browser/video | P2 | Optional Cog/WPE and VDE workers supply independent R4/R5 evidence/packages | Must not block stable desktop release unless explicitly included in its SLA. |
| 8. Release cleanup | P1 | Docs/release owner resolves Git hygiene, tags private candidate, writes install/recovery/how-to-contribute and publishes only after approval | R6 with a second-host/second-card reinstall demonstration. |

Parallelism: the image/packaging/upstream documentation lanes may run in isolated Git worktrees once source is frozen. Device/KMS changes remain serialized under the exclusive root operator and exact target identity. No OCP task, upstream MR, flash or change to an already running test is created by this design document.

## 10. Unresolved decisions and risks

1. **Upstream landing target:** verify the active libre-tegra/mesa repository/branch and preferred contribution channel; GitHub grate-driver/mesa is not necessarily writable canonical development. Ask maintainer before a large rebase.
2. **Which running code wins:** stable live musl/Sway (older than 0044) vs integrated 0044 host candidate. The release lock must be based on the **actual qualified** source, not latest timestamp.
3. **Kernel boot topology:** use MicroSD extlinux for the U-Boot-first v1 image; consider internal-kernel/one-shot kexec compatibility only as an explicitly separate profile.
4. **Sway hotfix retention:** do we still need the exact-1:1 wlroots filter patch with the final Grate shader and texture fixes? The A/B result decides, not tradition.
5. **Browser graphics:** WPE 2.54 requires Skia for 2D and the WebProcess compositor; changing the frontend alone will not bypass its shader burden. Earlier WPE 2.48/TextureMapper is a separately versioned historical alternative, not an invisible fallback.
6. **GLES2 truthfulness:** fragment uniform minimum (historically 32 scalars = 8 vec4), cube, dynamic control flow, unsupported stencil/blend cases, register pressure and sync remain explicit until proved. Keep caps conservative.
7. **Video:** VDE→KMS is a different display contract from VDE→Sway/Wayland. Current latter pixel failure remains a release note and blocker **only for that feature**, never “fixed by clean packaging”.
8. **Software supply chain:** private work trees and package caches may be the only copies of historical integrated code; make a verified, reviewed source snapshot before any hygiene work.
9. **Source/reference integrity:** preserve the two historical U-Boot/kernel/device models and dated test receipts; never rewrite them to agree with the eventual happy-path guide.

## 11. References / baseline for this design

- Local: docs/sl101-patch-atlas-20261106.md; docs/sl101-patch-inventory-20261106.md; docs/sl101-integrated-0044-qualification-20261106.md; docs/sl101-musl-sway-green-20261106.md; docs/sl101-video-sway-musl-20261106.md; docs/sl101-grate-production-20261004.md; docs/sl101-sway-i3-config-parity-20261106.md; docs/sl101-sway-egl-no-upstream-review-20261105.md; docs/sl101-kernel7-consolidation.md; docs/sl101-nura-flashable.md; docs/upstream/grate-mesa-submission-split-20261103.md; docs/upstream/grate-driver-github-community-review-20261103.md.
- [Mesa submission procedure](https://docs.mesa3d.org/submittingpatches.html).
- [Grate Mesa issue #19 / 2026 Tegra30 comparison and maintainer target discussion](https://github.com/grate-driver/mesa/issues/19).
- [Alpine APKBUILD tooling](https://wiki.alpinelinux.org/wiki/Creating_an_Alpine_package) and [Nura/postmarketOS packaging documentation](https://docs.postmarketos.org/pmaports/main/packaging/device-categorization.html).
- [WPE 2.54 graphics architecture](https://wpewebkit.org/blog/2026-09-16-wpewebkit-2.54.html).

**Definition of done for consolidation:** someone with no access to the current host’s ignored build/work trees can take the pinned repository state, build a native armv7/musl image, flash only a verified removable card, boot via existing U-Boot, recover from a failed desktop, verify actual Grate pixels and hashes, and understand exactly which optional browser/media features are not yet qualified.
