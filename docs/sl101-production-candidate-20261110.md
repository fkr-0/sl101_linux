# SL101 production-derived kernel candidate and five-lane desktop/media/browser gate

Date: 2026-11-10. **Status: boot-tested candidate; NOT default-production promotion.**
Canonical project: `sl101_linux`; NuraLoumi source is a sibling repository.

## 1. Kernel provenance, bug and candidate

The baseline is the *archived productive* `linux-postmarketos-grate-7.0.1-r4`
from the SL101 devices, source commit `bfffc6d6656e87f3de3aa4c09d852849081ef088`.
The original kernel and its matching initramfs/DTB/config/module tree are preserved in
`work/sl101-prod-dma-init-20261110/backup-prod-7.0.1/`.
Original productive vmlinuz SHA256:
`794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1`.
This baseline is **not** K76, the diagnostic kernel, nor the separately archived EC/LNX image.

Kernel `7.0.1-postmarketos-grate-dmafix1` is already built off-device with
`work/sl101-prod-dma-init-20261110/prepare-source.sh` and
`build-prod-dmafix.sh`; a second unnecessary kernel rebuild would waste storage.
The **only applied code patch** is
`patches/linux-postmarketos-grate-7.0.1/dmafix1/0002-dma-direct-zero-no-kmap.patch`
(SHA256 `b0796b4d6b50feebf0a6281833fbe468a8f89c3a1b9c31747aa9bf6a5b99c96b`).
It zero-initializes the `dma_direct_alloc_no_mapping()` pages and synchronizes
initial contents for non-coherent DMA. The separately archived ARM CMA remap
patch `0001` is **NOT applied**; `DMA_ATTR_NO_KERNEL_MAPPING` bypasses the
ARM contiguous allocation path for the relevant direct-DMA allocation.
Do not conflate these source branches or claim that the alias hypothesis was fixed.

Build facts: zImage SHA256
`315a49d41d590ee01eef59745fd0473e8e10f00fe547318f5b95d1219e0c4541`;
SL101 DTB `01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0`
matches stock; 587 `.ko.zst` modules with matching `modules.dep` and
verified `7.0.1-postmarketos-grate-dmafix1` vermagic.

**Hardware qualification so far:** One experimental APX-booted `.106`
ran the same first-use buffer matrix 216/216 clean, plus 108/108 clean after
page-cache churn, with zero relevant kernel warnings. The K76 diagnostic
comparison was 38/108 corrupt with automatic `DONT_KMAP`, 0/108 with it off.
On dmafix1, automatic DONT_KMAP remains on. Cog software mode loaded Wikipedia
on dmafix1. This is strong first-use regression evidence but not complete
functional, reboot, video, suspend or long-run qualification. See
`docs/sl101-0076-dontkmap-ab-20261109.md` for precise cases and limits.

### Canonical release candidate, without rebuilding or changing devices

The original historical archive `work/sl101-prod-dma-init-20261110/sl101-7.0.1-dmafix1-experimental.tar.zst`
contained a `lib/modules/.../build` symlink to an absolute host workspace path.
It must not be treated as a clean portable production package.

`scripts/sl101-prod-dmafix1-candidate.py` verifies the productive backup,
the exact applied patch, the built candidate, the 606 regular files in the
original release's SHA256SUMS, all 587 modules, release config and DTB.
`--package` performs an **idempotent refuse-overwrite** packaging pass,
removes the nonportable host `build` symlink in the new copy, adds
`release/PROVENANCE.json`, regenerates complete checksums and constructs
a deterministic tar/zstd archive. It leaves the original build/release untouched.

Commands from repository root (host only):

    python3 scripts/sl101-prod-dmafix1-candidate.py
    python3 -m unittest discover -s tests -p test_sl101_prod_dmafix1_candidate.py -v
    # Once, only if candidate does not already exist:
    python3 scripts/sl101-prod-dmafix1-candidate.py --package
    make test
    make check

New portable candidate:
`work/sl101-prod-dma-init-20261110/canonical-candidate/sl101-7.0.1-dmafix1-canonical-candidate.tar.zst`
SHA256 `7f0af633d3d6b63e881b60ac2698c788b96f965b8325644a4024c3f40f90b294`.
A sibling `.sha256` file identifies it. The archive was independently extracted and its 607 checksummed regular files, included patch, DTB, zImage, module count and kernel-config invariants rechecked. This is **candidate**, not blessed production. Current repository validation: `make test` 2006 passed (3 skipped), `make check` passed, and all 6 new focused candidate tests passed.
`verify-host.py` from the historical lane needs the temporary full extracted
kernel source and cannot be rerun after that source's cleanup; its *earlier*
`HOST_VALIDATION_OK` log is preserved. The new post-build verifier does not
pretend to revalidate the missing source tree.

**Promotion gate:** preserve original bootable stock image and module backup;
use only the documented recoverable APX/RAM U-Boot experimental route and exact
CID/host identity; verify stage hashes, image/DTB/module release match, repeated
cold boots and first-use matrix, then Sway native EGL/pixels, input, video,
Cog, Wi-Fi, power and rollback. Boot and permanent eMMC changes require a
distinct authorization and rollback evidence. A kernel may be labeled production
only after these gates, never solely because its builder exited zero.

## 2. Five integration lanes, in dependency order

### (a) Latest NuraLoumi with truthful top-right renderer

Upstream sibling `/home/user/code/nuraloumi` revision `ccf7e3a` includes the
transient Sway workspace switcher and provider-based renderer display.
On 2026-11-09 this exact commit's separate **musl ARMv7** and **glibc armhf**
GitHub Actions jobs succeeded; the general CI job failed in its **Test** step (format/check succeeded), and must be triaged before release.
For the Alpine `.106`, use the musl artifact; for Debian `.100`, use the
glibc artifact. Do **not** mix dynamic loaders, libraries or package trees.

The panel already classifies live `/proc/<compositor>/environ` plus
`maps` as `Pixman`, `GLES2` or `Grate`, with PID-reuse protection.
`/run/sl101-render-status` is now written by the device desktop
launcher to report **requested versus actual** backend and fallback reason.
Integrate it as an attributed evidence source/fallback to avoid incorrectly
reporting that requesting Grate means GPU output. UI labels should distinguish
`Pixman (CPU)`, `Grate EGL/GLES2 (GPU)`, `GLES2 (driver unverified)`,
and `Unknown`. Test with actual Sway PID, framebuffer/pixel evidence,
renderer switch, failed EGL startup/fallback and panel reload.

Deployment gate: retrieve the exact CI artifact + SHA, inspect ELF
architecture/ABI/no-NEON/DT_NEEDED, compare installed hashes, stage a backup,
install only matching target binaries, reload/restart only the panel component
(not all Sway) after checking the live desktop owner; verify top-right label,
workspace switcher and restore. Preserve the tablet's *live-only* Sway
background indicator when updating config.

### (b) GPU video in Sway

Sway/GLES2 Grate itself can run, but **Sway video is not yet an accepted
GPU video path**. Debian `.100` software H.264 → `mpv --vo=wlshm` showed
182 dropped frames at 640×360@24 but 0 drops at 320×180@15 (no audio).
Earlier VDE→I420/RGBx→Wayland showed black/corrupt pixels. Kernel
`tegra_vde` is a hardware decoder, *not* the GR3D compositor.

Next: prove `v4l2slh264dec` decoder and negotiated YM12/YU12 multi-plane
layout; correct plane pitches, YUV order and DMA-Buf ownership; then
validate a VDE DMABuf → Grate/Wayland import → Sway scanout pipeline
against software reference pixels with visible frames and frame-drop
counters. Verify active Sway EGL/Gallium process mapping, not merely
`WLR_RENDERER=gles2`. Until the VDE warning below is addressed, avoid
repeated hardware decode stress. Retain mpv wlshm low-res fallback.

### (c) GPU/hardware-decoded video in direct KMS

Debian `.100` on the original stock kernel **already successfully**
negotiated VDE H.264 → DMA-Buf `DMA_DRM/YU12` → `kmssink` on
1280×800 KMS, ran 17.25 s to EOS/exit 0 and restored Sway.
But the kernel emitted a **P1 mutex-owner warning** from
`tegra_decode_complete` / `tegra_vde_h264_decode_wait`.
That invalid unlock crosses tasks. Direct KMS video **must not** be
promoted while this remains. The independently reviewed VDE async
semaphore patch must first be ported to the exact production-derived
7.0.1 source, with a new release suffix and matching rebuilt modules,
then boot and failover qualified; do **not** silently graft it onto
the proven dmafix1 binary. Repeat decoder-only, KMS visual/pixel,
timing and audio tests with a compositor-stop **watchdog** and verified
DRM-master release/restore. Never run KMS player and Sway simultaneously.
See `debian-rootbind/VIDEO-VDE-KMS-20261109.md`.

### (d) Cog/WPE with JS injection in Sway

Cog 0.18.5 / WPE WebKit 2.54.0-2 armhf runs as a **Wayland client**
(`--platform=wl`) in the isolated Debian root.
The existing Sway `scripts/sl101-cog-session` launches Wayland Cog but
currently **does not pass `--web-extensions-dir`**. It therefore is
not the validated browser-chrome injection route.

The existing ARMHF extension source `tools/sl101-cog-web-extension/` and
`scripts/sl101-cog-extension-build.sh` support `window-object-cleared`,
each frame and navigation. Reuse the sandbox-visible
`/usr/lib/sl101-cog-extensions/libsl101-cog-inject.so` and snapshotted
`sl101-cog-script.js`. For the Sway launcher, prepare the snapshot
under chroot permissions before process start, add
`--web-extensions-dir=/usr/lib/sl101-cog-extensions`, and point
`SL101_COG_INJECT_SCRIPT` to the **sandbox-visible snapshot path**,
not a possibly hidden `/var/lib` source. Add dry-run and a no-inject
software fallback. Test that the extension runs on main document,
cross-origin/dynamic iframes and follow-up navigation. Browser GPU
mode remains separately opt-in; verify process-loaded EGL and visible
pixels. `--features=-UseDamagingInformationForCompositing` is important
for this Grate/WebKit combination (partial repaint artifacts).

### (e) Cog/WPE with JS injection in direct KMS

The KMS injection path already has source and prior hardware tests:
`scripts/sl101-cog-kms-integrated.sh`, `scripts/sl101-cog-enter-integrated.sh`
and `tools/sl101-cog-web-extension`. A prior device test found injected
chrome on 14/14 main/iframe navigation cases; the original visual
capture had GPU corruption and Cog's teardown status 139 on direct exit.
The newer Sway-aware KMS supervisor has host-test coverage but **not
a fully verified target watchdog/restore/pixel gate**. Do not confuse
KMS Cog with the ordinary Wayland Cog route.

First perform read-only hardware/lock/DRM-debugfs checks, module hash
checks and a short software KMS session while physically supervised.
Then bounded GPU KMS launch with extension active, actual
Cog/WebProcess GPU maps, frame oracle and forced-child/timeout
restore tests. Only one DRM master; verified Sway/input/panel restoration
is mandatory. Preserve software Cog and KMS recovery paths separately.

## 3. Decision table

| Lane | Present evidence | Release decision |
| --- | --- | --- |
| Kernel dmafix1 | Built; hash-pinned; 324/324 first-use cases; 587 matching modules | Candidate; do not flash as default |
| NuraLoumi | ccf7e3a musl and glibc artifact jobs green; generic CI red | Stage reviewed binary; test panel accuracy |
| Sway video | Software low-resolution usable; VDE→Wayland corrupt/black | GPU path blocked |
| KMS video | VDE DMA-Buf→KMS 17.25 s completed; mutex WARN | Blocked until VDE lock repair |
| Sway Cog + JS | Cog Wayland runs; injector exists but Sway launcher lacks wire-up | Implement/test extension hookup |
| KMS Cog + JS | Older injected DOM tests pass; GPU corruption/teardown risk | Supervised experimental only |

Do not merge the `.100` Debian rootbind (direct glibc) and `.106`
Alpine/musl host + Debian chroot as one device image. Promote capabilities
independently: kernel first-use success does not qualify VDE, Wayland
import, browser frame correctness or JS injection.
