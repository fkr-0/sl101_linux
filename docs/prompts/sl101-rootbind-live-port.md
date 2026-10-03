# ANDROID-SL101-ROOTBIND-LIVE-01 — finish the ASUS Eee Pad Slider RootBind port from live evidence

@projmgrauth
Set repo: android-infra.

Canonical lane: `ANDROID-SL101-ROOTBIND-LIVE-01`.

Continue the existing ASUS SL101 / Eee Pad Slider Linux work from the repository's verified state. This is **not** a fresh research task and must not rebuild known-good artifacts just because newer versions exist.

## Operator intent and identity note

The physical ePad Slider is now being worked on and may present a generic marketing/product label such as **Eee Pad Transformer**. That label is acceptable as a discovery clue and is not by itself a failure. However, never use a generic Transformer label to justify SL101-specific boot material. Confirm the physical slider and live ASUS/Tegra identity from independent properties before binding an exact serial or selecting `tegra20-asus-sl101.dtb`. If live evidence instead proves TF101/another board, stop the SL101 deployment path and report the mismatch rather than forcing it.

## Existing verified baseline — preserve it

Read fresh Git/status/claims plus `docs/sl101-linux.md`, `docs/fleet-roles.md`, `scripts/sl101-preflight.py`, `scripts/sl101-rootbind-build.py`, `scripts/sl101-rootbind-container-build.sh`, inventory identity files, tests and `tmp/sl101-rootbind/artifacts/provenance.json` before writes.

The existing host artifact set is already provenance-qualified:

- Linux `v6.18.45`, commit `bf3be28f6721e24961992ebb9e61c0cf21a56806`;
- exact `tegra20-asus-sl101.dtb`;
- matching kernel modules;
- Debian 13/Trixie `armhf` rootfs from snapshot `20260821T000000Z`;
- recorded artifact/config/package hashes in the current provenance manifest.

Preserve those bytes and hashes unless you identify and document a concrete defect. Do not substitute TF101 artifacts, historical partition numbers, old `abootimg` geometry, legacy `root=/dev/mmcblk*` guesses, or unverified SBK/BCT/key material.

Preserve all unrelated dirty/staged/untracked work. Never reset, clean, stash, bulk-format, delete, push, or publish.

## Phase A — reacquire the live tablet safely

Run current transport discovery. If an authorized tablet is visible, inspect **exactly one physical tablet at a time**:

- ADB/USB identity, exact serial and all relevant `getprop` identity fields;
- physical confirmation that it is the Slider SL101 rather than another Transformer-family device;
- CPU ABI/features needed by Debian armhf;
- Android build/kernel/cmdline;
- block devices, partition labels/sizes/symlinks and mount topology;
- `/data` backing device/filesystem and free space;
- root indicators without invoking `su` or escalating privileges;
- installed recovery/bootloader facts that can be observed read-only;
- current boot/recovery image header/geometry facts only where obtainable without writing;
- cable/key recovery paths and whether the tablet can be reliably rediscovered after ordinary disconnect/reconnect.

Use the normal android-infra scan/identify/inspect/snapshot flow plus `scripts/sl101-preflight.py`. Add an exact `sl101-1` or `sl101-2` serial binding only after the physical unit has been distinguished. Keep the other tablet/control identity untouched.

If the only visible label is “Eee Pad Transformer” but the physical device and lower-level properties consistently identify the SL101 family, record the generic label as a quirk rather than renaming the canonical device.

## Phase B — close the RootBind wrapper specification

Use **only** live tablet evidence to resolve the current blocked fields:

- ASUS boot image/header format for this unit;
- kernel and ramdisk load addresses/page size;
- exact boot partition label/path/size;
- exact Android data device/filesystem and hand-off needed to reach `/data/linuxroot`;
- whether a small SL101-specific initramfs or current-mainline hand-off patch is required;
- tested recovery path for restoring the original boot state;
- exact firmware/NVRAM filenames requested by the candidate Linux kernel, but only after runtime evidence exists.

First make the wrapper builder/specification deterministic and testable on the host. Preserve the original boot/recovery evidence and record SHA-256/byte-size provenance for every artifact involved.

Do not infer any unresolved field from TF101 guides or old repository archaeology. If one necessary field cannot be observed safely, leave it blocked and produce the narrow probe needed to obtain it.

## Phase C — prepare the RootBind userspace on the tablet

The intended first Linux milestone is Android-preserving RootBind with the already-built Debian armhf rootfs, not permanent U-Boot installation.

Once identity/storage/free-space/recovery gates are satisfied, prepare a reproducible `/data/linuxroot` staging plan and any required host-side extraction/configuration steps. Ensure:

- matching `/lib/modules/6.18.45` from the verified artifact set;
- unique machine-id and SSH host keys generated on first real boot, never baked into the archived rootfs;
- minimal network/SSH configuration with key-based access and no committed secrets;
- root target and mount sequence derived from this tablet's observed topology;
- Android data is not reformatted and unrelated user data is not overwritten;
- rollback can remove the staged rootfs without depending on Linux successfully booting.

## Phase D — first reversible boot milestone

The operator has asked to advance the RootBind port, but this lane does **not** authorize eMMC repartitioning, permanent U-Boot replacement, vendor-bootloader erasure, blind NVFlash, or destructive APX/Fusée operations.

A RootBind boot experiment may proceed only when the repository's recovery/backup gate is satisfied for the exact tablet: boot/recovery source partitions unambiguously identified, original images captured with sizes+SHA-256 to a host destination, restore procedure written from observed topology, and a tested path back to Android/recovery exists.

Prefer the least persistent mechanism compatible with the observed boot chain. If the only available method requires an irreversible/persistent bootloader change or unreviewed partition write, stop before it and produce the exact separately-authorized next lane instead.

For any permitted boot-image write, show/record the exact source artifact hash, destination identified by label+size+device path, backup hash, and rollback command before execution. Refuse any command whose destination identity is ambiguous.

## Linux validation order

A boot prompt or splash is not completion. Prove, in order:

1. kernel reaches userspace with the SL101 DT and matching modules;
2. rootfs storage is correct and Android data is not unexpectedly reformatted/mounted;
3. built-in keyboard, pointing/input devices, touchscreen, power/volume and slider/tablet-mode switch;
4. USB host/device behavior;
5. Wi-Fi enumeration, exact firmware/NVRAM request, association/DHCP/DNS and sustained SSH;
6. battery/charger/thermal telemetry;
7. audio/Bluetooth/display usability;
8. repeated suspend/resume and reboot/recovery back to Android.

Capture `dmesg`, module/firmware evidence and failures without hiding partial hardware support.

## Repository implementation and verification

Implement any necessary safe helper changes, wrapper builder, provenance fields, tests and operator documentation. Add regression tests for every newly encoded boot-header/layout invariant so a future run cannot silently fall back to historical guesses.

Run focused SL101 tests, the full unit suite, compile/shell checks, and `git diff --check`. Keep secrets/SBK/BCT/private recovery data out of Git.

## Deliverables

Finish with a precise state report containing:

- observed exact tablet identity and whether the generic “Eee Pad Transformer” label was only cosmetic;
- exact serial binding if proven;
- resolved vs still-blocked boot-wrapper fields;
- preservation check for the Phase-4 kernel/DTB/modules/rootfs provenance hashes;
- backup/recovery evidence and whether a reversible first RootBind boot was actually performed;
- Linux boot/hardware validation matrix with pass/fail/untested states;
- changed files and exact checks;
- exactly one bounded continuation only if the remaining step crosses an explicit destructive/persistent authorization boundary.

Do not claim success from host artifacts alone. The milestone is a reproducible, recoverable SL101-specific RootBind path grounded in the physical tablet.
