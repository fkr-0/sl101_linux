# ASUS Eee Pad Slider SL101 Linux feasibility

Research baseline: 2026-08-22. This document is planning evidence only; it does **not** authorize flashing, repartitioning, exploit/APX/NVFlash execution, APK installation, boot-partition writes, or bootloader replacement.

## 2026-08-27 research refresh

The upstream position is now sufficiently concrete to choose a split evaluation strategy without touching either tablet:

- Current U-Boot documentation explicitly supports the ASUS Slider with `sl101.config`, accepts `sl101` in the `re-crypt` processing flow, and documents APX/RCM preloading through `fusee-tools`. This is direct SL101 evidence, not a Tegra-2-family inference. The same documentation also warns that permanent U-Boot installation erases eMMC and replaces the vendor ASUS bootloader, so persistent installation remains outside the discovery phase.
- Mainline Linux SL101 support landed for the 6.18 cycle with an SL101-specific DTS and a real-device `Tested-by`. Kernel.org now lists 6.18.46 as the current 6.18 longterm point release (2026-08-23) and 7.2 as current mainline. The completed Phase-4 artifact set deliberately remains pinned to 6.18.45 for provenance; a one-point stable update by itself is not a reason to invalidate or rebuild verified artifacts before live hardware exists.
- The current postmarketOS `linux-postmarketos-grate` armv7 package ships `/boot/dtbs/tegra20-asus-sl101.dtb`. That materially lowers kernel-integration risk, but it still does not establish a maintained `device-asus-sl101` package, pmbootstrap device definition, installer, or tested end-to-end SL101 lifecycle. Treat postmarketOS as a credible stretch port target, not a turnkey install target.
- Linux Deploy remains a rooted Android chroot option and is conceptually closer to a classic RootBind/Linux-on-Android arrangement than PRoot. Termux/PRoot-Distro is actively maintained and convenient on supported Android versions, but current Termux only fully supports Android 7+; Android 5/6 has app-only compatibility without normal package support. A stock-era SL101 Android build is therefore not a good foundation for a modern Termux/AndroNix plan unless a sufficiently new custom ROM is already proven on the physical tablet.
- AndroNix is an orchestration layer around Termux + PRoot, so it does not remove the underlying Android-version or PRoot-overhead constraints. On Tegra 2 hardware, prefer native chroot/RootBind or direct-mainline execution over PRoot when root and a reversible boot path are available.

Recommended split once the tablets are physically identified:

1. `sl101-1`: **RootBind-first**. Preserve Android, use the already-built Debian armhf rootfs + matching mainline kernel/DTB, and complete only the missing tablet-specific boot-wrapper/recovery facts from live read-only inspection before proposing any boot experiment.
2. `sl101-2`: keep unchanged as the control device until `sl101-1` has a reproducible recovery path. Then evaluate a **RAM-only** U-Boot/APX preload as the next stretch milestone, with explicit operator approval and device-specific SBK/BCT/recovery evidence. Only after that should a postmarketOS direct-boot port be considered.

This split gives one low-risk path toward a usable Linux environment and one independent path toward full native Linux without sacrificing both tablets to the same boot-chain experiment.

## Phase-4 host artifact result and live boundary

The Phase-4 pass on 2026-08-22 completed the host-only artifact milestone without installing the missing cross-build dependencies on the workstation. The build ran in the pinned Debian container image `debian@sha256:b6e2a152f22a40ff69d92cb397223c906017e1391a73c952b588e51af8883bf8`, with the tracked checkout mounted read-only and generated work confined to repository-local `tmp/sl101-rootbind/`.

The concrete, verified outputs are:

| Artifact | SHA-256 |
|---|---|
| kernel `.config` | `2431173cadb597191042a28f77c0c4437bc9dc4e9bf0a4133ba0579e13c20ea7` |
| `zImage` | `b76cf9e35b730c86488913564b964578ed1d90d99a23d7e005146aa7a0551ba3` |
| `tegra20-asus-sl101.dtb` | `7c938df062396a142f800c3807ba0d8f4255cd9ff8bfc8d09e83ee93b1dcb52a` |
| matching modules archive | `7be10435bc15fc22ed511eb946b0d44302e578aac7be5585b79a7bdb2e52be64` |
| Debian Trixie armhf rootfs | `5bfc126bdb0c9d4df6048fa123f5af4cc14bda430ade81a865db9b6e3c20a460` |
| build-environment manifest | `17701252c4367dcb52e049c438c046a878ced0bb6ecddd74318d0c2a07937953` |
| build-environment package list | `0bd76b6ce200745d501486574e86aeec9a5492404c498101858f37ff289d693d` |
| rootfs dpkg package manifest | `3fa514ab63cc82a826f89644b6ec6ec03103a5d32c00ec7c49dc1ca0b7dfc173` |

`scripts/sl101-rootbind-build.py record` wrote `tmp/sl101-rootbind/artifacts/provenance.json` and verified the exact Linux source commit `bf3be28f6721e24961992ebb9e61c0cf21a56806`, kernel release `6.18.45`, SL101 DTS identity, required config floor, matching modules, Debian snapshot, build-tool package provenance, and archive hashes. Debian Trixie's merged-/usr layout is accepted only when the rootfs archive proves `/lib -> usr/lib`; the actual modules are under `usr/lib/modules/6.18.45`. The final provenance file itself hashed to `983ab1d29205d150ad805e2e55f4553467396511d7c87e6353d1ddd8ca58ab96` at the Phase-4 verification point.

The Debian snapshot frontend intermittently failed two individual package downloads during the first rootfs attempt. Recovery reused only objects whose SHA-256 values matched the signed armhf Packages metadata; `rootfs-recovery.json` records and the final recorder re-verifies `adduser_3.152_all.deb` (`e50984d2e1ef6300e3fd51303839842189a077b10cb5cadff1923df10c61c493`) and `libaudit1_4.0.2-2+b2_armhf.deb` (`9b2f16d1ee4f734456182237178c31882fcfd0166d3b6f4af26a232123dbef6e`). No firmware package was selected. The rootfs has no generated SSH host keys, has an empty machine-id, and the host QEMU helper is not part of the archived target filesystem.

The workstation itself still lacks `arm-linux-gnueabihf-gcc`, `debootstrap`, and `qemu-arm-static`; that is intentional because Phase 4 satisfied those prerequisites only inside the isolated container.

The same live-device blocker remains: `adb devices -l`, android-infra scan/identify, `fastboot devices -l`, and relevant USB visibility all found no SL101. Therefore Phase 4 adds no serial, partition, root, recovery, SBK, BCT, bootloader, boot-image geometry, or firmware-runtime fact, and `scripts/sl101-preflight.py` was not run.

The boot-wrapper contract remains `blocked-pending-live-device-evidence` with `artifact: null`. None of the completed host artifacts is a persistent bootloader image or a deployable RootBind wrapper.

## Phase-3 live evidence and boundary

The Phase-3 discovery pass on 2026-08-22 again found **no SL101 transport**:

```text
adb devices -l          -> no devices
android-infra scan      -> {"adb": [], "fastboot": []}
android-infra identify  -> []
fastboot devices -l     -> no devices
relevant lsusb filter   -> no ASUS/NVIDIA/Android target
```

This preserves the Phase-2 hardware blocker. Neither tablet has been observed, physically distinguished, or mapped to an exact serial, and Phase 3 therefore adds **no** serial rule, partition fact, root/recovery fact, SBK/BCT fact, bootloader fact, or boot-image geometry. The two family-level SL101 identity rules remain deliberately ambiguous.

Phase 3 is host-only preparation. `scripts/sl101-rootbind-build.py` now describes and verifies a pinned kernel/rootfs artifact contract, but intentionally has **no boot-wrapper construction command** until a physical tablet supplies the missing boot/recovery facts. Its `doctor` check currently reports three host prerequisites absent on this workstation: `arm-linux-gnueabihf-gcc`, `debootstrap`, and `qemu-arm-static`. No kernel/rootfs artifacts were built in this phase, so no artifact hashes are claimed yet.

## Phase-2 decision

The safest 2026 path is still **Android-preserving RootBind first**, but the rationale is now stronger and more precise:

1. establish the exact identity, partition map, root/recovery state, CPU features, and rollback path on one physically labelled SL101;
2. build a modern Debian armhf rootfs on the host and pair it with a current SL101-capable mainline kernel/DTB;
3. prove the kernel/rootfs combination through the least invasive RootBind-compatible boot method that the live recovery/partition evidence actually supports;
4. validate storage, input, Wi-Fi/firmware, charging/battery, suspend/resume, and recovery before treating the tablet as usable Linux hardware;
5. consider U-Boot/direct-mainline or postmarketOS installation only as a separately authorized later phase.

The important Phase-2 correction is that **SL101 upstream support is no longer hypothetical**. Linux gained an SL101 device tree for the 6.18 cycle, current kernel trees contain `tegra20-asus-sl101.dts`, current U-Boot documentation has an explicit `sl101.config` and SL101 processing path, and postmarketOS' current `linux-postmarketos-grate` package contains `tegra20-asus-sl101.dtb`. Those facts reduce board-support uncertainty. They do **not** make persistent bootloader installation safe or turnkey.

## Evidence ranking

| Rank | Evidence | What it proves | What it does not prove |
|---|---|---|---|
| A | Linux Tegra 6.18 pull + SL101 patch, tested on an SL101 | Mainline kernel has an SL101-specific DT and shared Tegra20 Transformer hardware description. | A particular tablet's boot/recovery chain, firmware completeness, or userspace readiness. |
| A | Current U-Boot ASUS Transformer-T20 documentation | U-Boot now has `sl101.config`, `re-crypt --dev sl101`, and an SL101/T20 preload/install flow. | Safety of persistent installation; the documented permanent install erases eMMC and requires the device's individual SBK. |
| A/B | Current postmarketOS package index | `linux-postmarketos-grate` on `main` ships `tegra20-asus-sl101.dtb` (current package line is newer than the v25.06 package, which lacked that DTB). | A maintained `device-asus-sl101` package, pmbootstrap device definition, installer, or tested SL101 lifecycle. None was found in the current package/device searches performed for this audit. |
| B | Repository-local `sl101_linux` tree | Historical SL101-specific kernel work appended `tegra20-asus-sl101.dtb` and targeted RootBind. | Safe current boot-image geometry or partition numbers. Its own README is uncertain about the boot partition. |
| B/C | Historical RootBind material | Android-preserving `/data/linuxroot` is a plausible architecture and SL101-compatible recovery work existed. | Compatibility of old kernels, installers, Debian/Ubuntu images, or partition commands with either physical tablet today. |
| C / negative | TF101 Linux-image and TF101 APX tooling | Strongly documents what **not** to copy: TF101 U-Boot/NVFlash procedures were explicitly unsupported for SL101 and can repartition/erase the device. | SL101 behavior. TF101 success is not SL101 success. |

## Linux 6.18+ mainline state

The September 2025 patch `ARM: tegra: add support for ASUS Eee Pad Slider SL101` added `arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dts`, factored common Transformer hardware into `tegra20-asus-transformer-common.dtsi`, and carried an explicit `Tested-by` for an ASUS SL101. The Tegra device-tree pull for `v6.18-rc1` includes that change. The SL101 fragment identifies `compatible = "asus,sl101", "nvidia,tegra20"`, describes the Atmel MXT1386 touchscreen and the slider/tablet-mode switch, while common TF101/SL101 hardware remains in the shared include.

This is materially better evidence than the old local `clamor-s/linux` SL101 branch: for a new build, use a released/current mainline-derived source that contains the upstream SL101 DTS rather than treating the historical branch as the source of truth.

### Kernel build acceptance gate

A candidate kernel is not accepted just because `tegra20-asus-sl101.dtb` exists. Before any device write, record on the host:

- exact kernel source/tag/commit and config;
- SHA-256 of kernel, DTB, modules archive, and any boot-image wrapper;
- presence of the exact `tegra20-asus-sl101.dtb`, not TF101/TF101G substitution;
- the intended root device/rootfs path derived from live evidence, not copied from an old command line;
- module/kernel release match;
- firmware files required by the drivers actually reported by that kernel.

### Phase-3 pinned kernel contract

The host build baseline is deliberately explicit:

```yaml
kernel:
  upstream: https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
  selected_ref: v6.18.45
  selected_commit: bf3be28f6721e24961992ebb9e61c0cf21a56806
  current_mainline_observed_2026_08_22: v7.2
  architecture: arm
  cross_compile: arm-linux-gnueabihf-
  config_seed: multi_v7_defconfig
  dt_source: arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dts
  dt_artifact: arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dtb
```

`v6.18.45` is selected rather than merely saying "current kernel" because it is a released 6.18 longterm revision whose peeled Git tag resolves to the commit above, and that exact source contains the SL101 DTS. Current mainline `v7.2` is recorded as contemporaneous evidence, not silently substituted into the build. The helper refuses to record provenance if the checked-out kernel commit differs from the pinned commit or if the SL101 model/compatible strings are absent.

The seed `multi_v7_defconfig` already enables the acceptance-floor drivers described by the upstream SL101/common DTS, including Tegra, eMMC/MicroSD, Atmel maXTouch input, brcmfmac, Bluetooth HCI BCM, GPIO charger, SBS battery, RTC, USB, and Tegra DRM. `scripts/sl101-rootbind-build.py record` validates the required symbols before hashing a build. This is a **configuration floor**, not evidence that either physical tablet has successfully exercised those drivers.

## Phase-3 RootBind kernel/rootfs artifact contract

The reproducible preparation boundary is split into what can be known on the host and what remains blocked on live hardware.

### Host-buildable artifacts

`scripts/sl101-rootbind-build.py plan` emits the exact repo-local plan under `tmp/sl101-rootbind` by default. The contract is:

1. clone the upstream stable kernel at tag `v6.18.45`, detach at exact commit `bf3be28f6721e24961992ebb9e61c0cf21a56806`, and verify the SL101 DTS;
2. build `multi_v7_defconfig`, `zImage`, DTBs, and modules with the GNU/Linux armhf cross-toolchain prefix `arm-linux-gnueabihf-`;
3. stage modules with `INSTALL_MOD_PATH` and inject that exact module tree into the Debian rootfs;
4. bootstrap Debian 13/Trixie `armhf` from the dated Debian snapshot `20260821T000000Z`, using the documented `--foreign` + QEMU second-stage flow on this x86_64 host;
5. keep userspace minimal (`ca-certificates`, `iproute2`, `iputils-ping`, `iw`, `kmod`, `openssh-server`, `procps`, `systemd-sysv`, `udev`, `wpasupplicant`), remove generated SSH host identity and the QEMU helper before archival, and record an exact package manifest;
6. archive the matching modules and rootfs with deterministic path ordering and normalized stored mtimes;
7. use `record` to verify the pinned kernel source/config and SHA-256 the kernel config, `zImage`, SL101 DTB, modules archive, and rootfs archive into a provenance manifest.

Archive metadata normalization makes repeated outputs more comparable, but the manifest deliberately attests to the **concrete** source commit, Debian snapshot contract, kernel config, matching module layout, package manifest, and artifact bytes. It does not claim that arbitrary host tool versions produce bit-identical root filesystems. The rootfs stage additionally requires root privileges or an explicitly configured equivalent user-namespace/container environment for `debootstrap`/`chroot`.

### Firmware policy and runtime gates

The upstream Transformer common DTS identifies an AzureWave AW-NH615 / BCM4329B1 SDIO Wi-Fi function (`brcm,bcm4329-fmac`) and related BCM4329 Bluetooth. This is enough to require `brcmfmac`/Bluetooth driver coverage in the kernel config, but **not** enough to select a firmware filename by analogy with TF101 guides. The initial rootfs contract therefore contains no guessed firmware package. After a future Linux boot, record the exact firmware/NVRAM filenames requested by the selected kernel and then add only the matching, provenance-recorded files/package.

The first hardware validation gate remains:

- input: MXT1386 touchscreen, power/volume keys, SL101 `SW_TABLET_MODE` slider switch, and built-in keyboard/pointing controls if exposed;
- Wi-Fi: BCM4329B1 enumeration, exact firmware/NVRAM request, successful firmware load, association/DHCP/DNS, sustained ping and SSH;
- power: SBS battery values, GPIO charger/mains detection, thermal telemetry, and repeated suspend/resume without losing input/Wi-Fi/storage/display;
- storage: unambiguous eMMC/MicroSD identity and a RootBind root target derived from live mounts/partition labels rather than a historical device number.

### Boot wrapper remains intentionally incomplete

A deployable RootBind boot image **cannot be truthfully derived yet**. Phase 3 records the missing fields instead of filling them from archaeology:

```yaml
boot_wrapper:
  status: blocked-pending-live-device-evidence
  build_command: null
  unresolved:
    - ASUS boot image/header format used by the observed tablet
    - kernel/ramdisk load addresses and page size
    - exact boot partition label, path and size
    - whether current mainline needs a device-specific initramfs or RootBind hand-off patch
    - exact /data filesystem/device and mount sequence needed to reach /data/linuxroot
    - tested Android/recovery restore path for that same tablet
```

The legacy `mmcblk0p9`/`mmcblk0p4` guesses, `root=/dev/mmcblk1`, old `abootimg` addresses, TF101 blob/NVFlash procedures, and historical SBK/BCT/key material are explicitly quarantined and never used as defaults by the helper. No persistent bootloader artifact is part of this contract.

## Audit of repository-local historical commands

The historical tree is valuable evidence but contains commands that must be treated as **quarantined examples**.

### `devices-trunks/sl101/sl101_linux/README.org`

It proposes writing a built kernel directly to `/dev/mmcblk0p9` and immediately admits the boot partition may instead be `/dev/mmcblk0p4`. That uncertainty is a hard stop. Neither partition number may be used on a physical tablet until the tablet's own partition labels, sizes, symlinks, boot/recovery images, and restoration procedure agree.

### `devices-trunks/sl101/sl101_linux/build_kernel/make_tegra.sh`

The script hard-codes legacy Android boot-image geometry and a kernel command line including `root=/dev/mmcblk1`, fixed Tegra memory parameters, and `tegraboot=sdmmc`. It builds the historical `clamor-s/linux` `sl101` branch using `transformer_defconfig`, an old bare-metal ARM toolchain, `abootimg`, and TF101-era blob tooling. The companion container is Ubuntu Xenial. These values are archaeology, not a modern build contract.

For Phase 2, retain the script unchanged as historical evidence and independently derive every boot-image address, root target, and wrapper requirement from the live device and the selected modern boot method.

### `devices-trunks/sl101/TF101-linux-images/*`

The mainline TF101 guides explicitly say SL101/TF101G are unsupported by their U-Boot/NVFlash procedure and describe an operation that formats/recreates the TF101 partition table. The older downstream guide contains TF101-specific direct writes and fixed partition assumptions. The bundled `android-tf101-tools` README also states that its tools do not work on SL101.

These are **TF101-only negative evidence**. Do not translate TF101 partition numbers, SBK handling, Wheelie/NVFlash commands, or recovery blobs into SL101 instructions.

### `devices-trunks/sl101/tetra20-fusiigelee/*`

The local tree contains an SL101 BCT and an old NVFlash command containing a hard-coded key. Treat that key and command as unverified historical material: do not reuse, publish as a device fact, or execute it. A BCT filename proves that someone prepared SL101-oriented tooling; it does not prove ownership, provenance, matching hardware revision, or recoverability of either tablet.

## Fusée Gelée / CVE-2018-6242 re-evaluation

The Phase-1 wording that public T20 support is merely "WIP" is too pessimistic in 2026. NVD describes CVE-2018-6242 as a BootROM RCM buffer overflow affecting some pre-2016 NVIDIA Tegra processors and enabling unverified code execution with physical USB/RCM access. More importantly for this exact family, current upstream U-Boot documentation now tells ASUS Transformer-T20 users to preload U-Boot in APX/RCM using `fusee-tools`, names `sl101` as a valid device codename, and requires the tablet's **individual SBK** for processing/install recovery.

That is credible evidence of a modern SL101-specific tooling chain, but it remains **research-only here** for three reasons:

1. no physical SL101 has been observed in this phase, so its APX identity, SBK provenance, BCT, and recovery state are unknown;
2. the documented persistent U-Boot installation explicitly erases eMMC and replaces the ASUS bootloader;
3. the user has not authorized exploit/APX/NVFlash execution or any bootloader write.

Therefore Fusée is no longer dismissed as "unsupported T20", but it is also **not the Phase-2 implementation path**. A later phase may evaluate a RAM-only preload as a potentially reversible test only after device-specific recovery evidence and explicit authorization; this document does not authorize that test.

## U-Boot/direct-mainline state

Current U-Boot documentation for the ASUS Eee Pad Transformer/Slider T20 family lists configuration fragments `tf101.config`, `tf101g.config`, and `sl101.config`. It also documents `re-crypt.py --dev ... sl101`, then a Fusee/APX preload path. This resolves the old question of whether modern U-Boot has an SL101 target: **yes**.

The same document is equally clear that permanent installation replaces the ASUS bootloader, makes vendor Android firmware unusable in that state, and erases eMMC during installation. That path is intentionally deferred. The first Linux milestone should preserve Android and avoid making U-Boot the recovery dependency.

## postmarketOS state

The current package index gives one useful positive signal: `linux-postmarketos-grate` on the main branch ships `/boot/dtbs/tegra20-asus-sl101.dtb`. The current main package line has advanced beyond the older v25.06 package, whose contents show TF101 but not SL101, so the SL101 DTB is a real recent improvement.

However, searches of the current public package/device surfaces performed on 2026-08-22 did **not** surface a maintained `device-asus-sl101` package or an SL101-specific pmbootstrap install/boot recipe. This is absence-of-evidence rather than proof that no out-of-tree port exists. It means the safe planning assumption remains:

> postmarketOS provides useful current Tegra kernel packaging, but SL101 is a port/integration target rather than a turnkey supported device installation.

Do not infer SL101 installability from the historical `asus-tf101` postmarketOS material in this repository.

## Modern Debian armhf rootfs strategy

Debian 13 (Trixie) is the preferred userspace baseline for the first native-Linux milestone. Debian's current installer documentation still supports 32-bit hard-float ARMv7 (`armhf`) and documents `debootstrap` as the official base-system bootstrap path. Debian armhf requires ARMv7 with VFPv3, so the live preflight must confirm the CPU feature set before the rootfs is treated as accepted.

Build the rootfs on the host rather than upgrading an ancient RootBind image in place:

1. create a fresh host-side workspace under the repository's designated build/tmp area or another explicitly chosen host path;
2. bootstrap Trixie armhf with current `debootstrap --arch=armhf` (use the documented foreign-architecture second stage when the host cannot execute armhf directly) or an equivalent auditable `mmdebstrap` flow;
3. keep the first image minimal: base system, CA certificates, SSH, networking tools, diagnostics, and only the firmware proven necessary by the candidate kernel;
4. install the **matching externally built SL101 kernel modules** into `/lib/modules/<release>`; do not assume Debian's generic ARM kernel is the SL101 boot kernel;
5. record package manifest, rootfs creation command, mirror/suite, date, and hashes;
6. add a graphical stack only after console/SSH, storage, network, input, and power behavior are stable.

### Firmware policy

Historical TF101 material refers to Broadcom Wi-Fi firmware, but do not promote TF101 filenames into SL101 configuration by analogy. Determine the Wi-Fi device/driver from the SL101 DTS plus live kernel logs/hardware enumeration, then package exactly the firmware requested by that driver. Record every firmware filename and its package/source.

## Read-only SL101 preflight

`scripts/sl101-preflight.py` is the Phase-2 host tool. It requires an already-authorized exact ADB serial and records curated observations only:

```sh
adb devices -l
python scripts/sl101-preflight.py --serial SERIAL
```

The default report is host-side under `state/sl101-preflight/<serial>/`. `--stdout` performs no host-file write. The probe uses only observational ADB shell commands (`getprop`, `cat`, `uname`, `id`, `df`, read-only `mount`, and `ls`). It intentionally does **not** invoke `su`, `adb root`, `dd`, `adb push/pull`, reboot, recovery entry, mount changes, package operations, or any flash command.

Capture one report per physically labelled tablet before adding an exact serial rule. If both tablets expose the same family properties, keep the inventory match ambiguous until the operator has physically distinguished which serial belongs to `sl101-1` and `sl101-2`.

## Reversible preflight / backup / recovery gate

No boot-kernel or bootloader experiment should proceed until all items below are supported by tablet-specific evidence.

### Identity and topology

- [ ] Physical label and observed ADB serial agree.
- [ ] ASUS/SL101 model evidence captured from the same transport.
- [ ] `/proc/cpuinfo` confirms the chosen userspace architecture baseline.
- [ ] `/proc/partitions`, `/proc/emmc`/`/proc/mtd` when present, mounts, and block symlinks are archived.
- [ ] Boot, recovery, system, data, cache, and any Tegra bootloader/BCT regions are mapped by label/size rather than guessed partition number.
- [ ] Current kernel command line and Android bootloader/build are archived.

### Root and recovery capability

- [ ] Root state is established without assuming a visible `su` binary means root access works.
- [ ] Exact custom recovery name/version is known, or recovery is explicitly recorded as unknown/stock.
- [ ] Recovery can see the relevant storage and can restore the current boot image.
- [ ] The operator has a tested physical key/cable procedure for returning to Android/recovery; APX is not counted as "tested recovery" unless separately authorized and actually validated.

### Backups before any future write

- [ ] Exact boot and recovery partition sources are independently identified.
- [ ] Read-only image capture method is reviewed before use; no historical `dd of=/dev/...` command is reused.
- [ ] Host has enough free space and backup destination is outside the device being changed.
- [ ] Captured images have byte sizes and SHA-256 hashes recorded.
- [ ] At least one known-good Android/vendor recovery artifact is available offline.
- [ ] Restore commands are written from the observed layout and reviewed **before** the write experiment.
- [ ] Any individual SBK/BCT material is stored as sensitive recovery data, not committed to Git or copied from the historical tree without provenance.

## Hardware validation matrix for the first Linux boot

A kernel reaching userspace is only the start. Validate in this order so failures are attributable:

| Area | Minimum evidence before milestone passes |
|---|---|
| Console / boot | Complete boot log or console evidence; correct SL101 DT model; no rootfs/module mismatch. |
| Storage | Rootfs stays read/write where intended; Android data is not unexpectedly reformatted/mounted; microSD and internal storage identities are unambiguous. |
| Input | Touchscreen events, power/volume keys, slider/tablet-mode switch, built-in keyboard/pointing controls if exposed, and USB input where available. |
| Wi-Fi | Driver enumerates; exact requested firmware identified and loaded; association, DHCP, DNS, sustained ping/SSH tested. |
| Power | Battery percentage/status plausible; charger detection works; thermal readings available; no unexpected discharge while plugged in. |
| Suspend/resume | Multiple suspend/resume cycles without losing input, Wi-Fi, storage, or display; failure leaves a recoverable console path. |
| USB | Host/device mode expected for the selected kernel; no dependence on an unverified recovery cable state. |
| Later | Audio, Bluetooth, acceleration, sensors, desktop/session power management after the base milestone is stable. |

## Next safe phase

Two independent, non-device-changing tracks are safe next:

1. satisfy the host prerequisites reported by `scripts/sl101-rootbind-build.py doctor`, then build the pinned `v6.18.45` kernel/DTB/modules and Debian Trixie armhf rootfs under repo-local `tmp/sl101-rootbind`; run the helper's `record` gate and preserve the resulting provenance hashes;
2. if an SL101 becomes physically available, attach and authorize **one tablet at a time**, run `adb devices -l`, the normal android-infra scan/identify/inspect/snapshot flow, and `scripts/sl101-preflight.py`; physically distinguish the tablet before adding an exact `sl101-1`/`sl101-2` serial rule.

Only after the live report establishes the actual boot/recovery layout and RootBind hand-off can a boot-wrapper construction contract be completed. Even then, stop before `su`, root escalation, push/pull, reboot/recovery entry, `dd`, mount changes, APK operations, APX/Fusée/NVFlash, fastboot flash, repartitioning, bootloader replacement, or any other device-changing action unless a later phase explicitly authorizes it with a concrete backup/restore plan.

## Sources consulted

Current/upstream:

- Linux Tegra v6.18 DT pull: https://www.spinics.net/lists/linux-tegra/msg84278.html
- SL101 DTS patch and real-device Tested-by: https://www.spinics.net/lists/linux-tegra/msg84445.html
- Linux kernel release state: https://www.kernel.org/
- Selected stable source tree containing `tegra20-asus-sl101.dts` at `v6.18.45`: https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dts?h=v6.18.45
- Current U-Boot ASUS Transformer-T20 documentation: https://docs.u-boot.org/en/latest/board/asus/transformer_t20.html
- postmarketOS `linux-postmarketos-grate` package contents: https://pkgs.postmarketos.org/contents?arch=armv7&branch=main&name=linux-postmarketos-grate&repo=postmarketos
- postmarketOS Tegra armv7 platform notes: https://wiki.postmarketos.org/wiki/Nvidia_Tegra_armv7_(nvidia-tegra-armv7)
- Debian 13/Trixie armhf installation guide: https://www.debian.org/releases/trixie/armhf/
- Debian debootstrap appendix: https://www.debian.org/releases/trixie/armhf/apds03.en.html
- Debian snapshot used by the Phase-3 rootfs contract: https://snapshot.debian.org/archive/debian/20260821T000000Z/
- NVD CVE-2018-6242: https://nvd.nist.gov/vuln/detail/CVE-2018-6242
- Linux Deploy: https://github.com/meefik/linuxdeploy
- Termux application support policy: https://github.com/termux/termux-app
- Termux PRoot-Distro: https://github.com/termux/proot-distro
- AndroNix PRoot backend: https://github.com/AndronixApp/AndronixOrigin

Repository-local historical evidence:

- `devices-trunks/sl101/rootbind.md`
- `devices-trunks/sl101/sl101_linux/README.org`
- `devices-trunks/sl101/sl101_linux/build_kernel/make_tegra.sh`
- `devices-trunks/sl101/sl101_linux/build_kernel/Dockerfile`
- `devices-trunks/sl101/TF101-linux-images/README.md`
- `devices-trunks/sl101/TF101-linux-images/README.Debian11Bullseye.md`
- `devices-trunks/sl101/TF101-linux-images/README.old.postmarketos-downstream.md`
- `devices-trunks/sl101/android-tf101-tools/README.md`
- `devices-trunks/sl101/tetra20-fusiigelee/instr.md` and `fusee-tools/README.md`
