# SL101 Nura bring-up — 2026-09-30

Use the persistent-U-Boot tablet at `root@192.168.23.166` as the first
Nura target. The operator identifies `.106` as the APX/fusee-gelee unit;
its changed SSH host key has not been accepted. Do not equate these roles
with the stale `sl101-1` / `sl101-2` inventory IDs without a physical mapping.

Nura is the new name for postmarketOS:
<https://nura.eco/blog/2026/09/27/nura-rename/>.

## Verified reference tablet

- Debian 13 Trixie armhf, Linux 6.18.45 build #5, SL101 device-tree model.
- Wi-Fi MAC `74:2f:68:74:ff:c8`.
- eMMC CID `7001004d4d43333247448d402a656e00`.
- SD CID `035344534c31323880ac79a543010300`.
- Root filesystem `/dev/mmcblk1p1`, UUID
  `369970cd-b2cf-4eae-bdcc-1d87e161bec5`; 128 GB card with a 29.7 GiB partition.
- AT keyboard, maXTouch touchscreen, DRM card and render nodes enumerated.
- AC online; battery 99% during preflight.
- Default extlinux entry uses `/boot/zImage-ec-current` and
  `/boot/tegra20-asus-sl101-ec-current.dtb`.

Reference hashes before and after GPU smoke:

```text
ab170625dbe038965d3c91a684e9153a91ad0e590edcd47c275c1ff3a7495766  zImage-ec-current
7533523688c510723064187167076ec5261ca0248e66860b01596f65706c426b  tegra20-asus-sl101-ec-current.dtb
569eb48ee45015477342e788237ba7257d78d8e03acd117606ee54480656acbc  extlinux/extlinux.conf
```

## Existing GPU work and live result

The implementation is in the Git-ignored directory
`devices-trunks/sl101/grate-mesa-build/`. It includes the Mesa 25 port,
build-system patches, a Debian armhf package, and an older-stack alternative.
Do not restart those port phases from the prompt documents.

The reviewed Mesa 25 package and deploy script still match:

```text
366aadb732af038ccc527a1a5a5ccb788532b39a93e0772f5105c9fea911da66  grate-mesa25-armhf.tar.gz
95b437b7cfa34abfe969f895e328ad10dff503324d18da8e5b3d508200c905f9  deploy-and-test.sh
```

Installed diagnostic prerequisites (`labwc`, `mesa-utils`, `file` and dependencies)
on `.166`; no package upgrades or removals were requested. Suppressed service
startup during installation; seatd is disabled/inactive. No persistent compositor
service was created. Removed the temporary package-startup policy afterwards.

Stock pixman labwc survived an eight-second bounded probe. The reviewed overlay
smoke returned 2: GPU labwc exited with EGL initialization failure; pixman survived.
`eglinfo` advertised grate but failed with repeated
`grate_channel_create() failed: -22` and a `ralloc.c` canary assertion. This is
**not GPU rendering success**.

The live `/proc/config.gz` lacks `CONFIG_DRM_TEGRA_STAGING`. The pinned 6.18.45
source guards channel ioctls behind that option, which depends on `CONFIG_STAGING`.
Direct `DRM_IOCTL_TEGRA_OPEN_CHANNEL` probes for GR2D (`0x51`) and GR3D (`0x60`)
both returned `EINVAL`. This establishes a missing kernel interface independently
of Mesa. The allocator assertion remains a separate userspace concern until
retested with channel support enabled.

Restored stock Mesa using
`/var/backups/grate-mesa25-20260930-090306/restore.sh`. The restored pixman probe
again survived eight seconds; SSH and Wi-Fi remained active; `dpkg --audit` was
empty; boot hashes above remained unchanged. Diagnostic packages remain installed.

Live logs remain under `/root/grate-mesa25-smoke/` and `/tmp/grate-mesa25-*.log`.
Host copies are under `tmp/sl101-nura/evidence/`.

## Nura starting point

Use the existing generic `nvidia-tegra-armv7` port, currently in `device/testing`.
An SL101-specific device package is not a prerequisite for the first boot.

Source snapshots:

- pmaports: `bfa93e645532689e9400827cf37feaf2f2a5a5cd`.
- pmbootstrap 3.11.1: `4b4f024f8c1d7acc9db6d66bab6f19fe7d1dd1b3`.
- Source checkouts: `tmp/sl101-nura-pmaports`, `tmp/sl101-nura-pmbootstrap`.
- Isolated config/work: `tmp/sl101-nura/pmbootstrap.cfg`, `tmp/sl101-nura/work`.
- Selected UI/init: console/OpenRC. SSH key selection is only `~/.ssh/id_rsa.pub`.
- Image build account: `user`; password is a disposable build-test credential.

The current package recipe selects `linux-postmarketos-grate` 7.0.1-r4,
source `https://codeberg.org/libre-tegra/linux`, commit
`bfffc6d6656e87f3de3aa4c09d852849081ef088`. Its config enables
`CONFIG_DRM_TEGRA_STAGING=y`. Inspect the actual installed package version,
SL101 DTB, keyboard behavior and Wi-Fi firmware before relying on it.

Host rootfs build succeeded using the published kernel 7.0.1-r4. The installed
config confirms both `CONFIG_STAGING=y` and `CONFIG_DRM_TEGRA_STAGING=y`.
The DTB contains an EC/serio node, but uses the grate `asus,ec-dock` /
`asus,ec-kbc` drivers, rather than Debian's newer Transformer EC series. Physical
keyboard behavior must therefore be retested. The firmware package contains
`brcmfmac4329-sdio.bin`, SL101-specific NVRAM and an SL101 Bluetooth file.

The SD image build also completed successfully. Prepared artifact:
`tmp/sl101-nura/output/sl101-nura-edge-20260930.img` (1537 MiB).
`tmp/sl101-nura/output/SHA256SUMS` records its final hash. Its boot partition
explicitly selects `/tegra20-asus-sl101.dtb`, replacing the generic `fdtdir /`
entry, so boot does not depend on an unverified U-Boot `fdtfile` variable.
It contains separate `pmOS_boot` and `pmOS_root` filesystems and UUID-based
initramfs arguments. The host chroots were shut down after image creation.
No physical SD card or tablet partition was written; no Nura hardware boot
has been performed.

Debian's GPU binary package uses glibc and cannot be copied into Nura's musl
userspace. Reuse the driver source/build-system work for a separate Nura build.
The stock generic port does not itself prove grate 3D acceleration on SL101.

## Boot acceptance and next work

1. Prepare a separate image/rootfs; choose a spare SD card or explicitly selected
   alternate storage arrangement before any partition or boot-default changes.
2. Preserve the Debian SD filesystem and its default boot entry; retain an
   immediately selectable Debian boot route for experimental kernels.
3. Validate the Nura kernel, SL101 DTB and matching modules as one set. First
   prove keyboard, display/backlight, touchscreen, Wi-Fi/SSH and charging.
4. Test grate channel open with the staging interface enabled, then a compatible
   musl Mesa/libdrm build. Record the actual GL renderer and a rendered workload;
   EGL enumeration, DRM nodes and a running compositor alone are insufficient.
5. Recheck suspend/resume and cold SD boot before proposing maintained upstream
   SL101 support. Keep the APX-dependent tablet as the Debian comparison unit.

Rootfs preparation alone is not a Nura boot, and a chroot smoke test is not
hardware validation of Nura's kernel.

## Current-card overwrite authorization and deployment preparation

On 2026-09-30 the operator explicitly authorized overwriting the persistent
U-Boot tablet's current SD card; the other card holds a mirrored Debian install.
This supersedes the spare-card/alternate-installation requirement above.
The exact `.166` SD CID was rechecked, with AC online and battery at 99%.

Prepared `tmp/sl101-nura/output/sl101-nura-edge-sl101166.img` with the tablet's
Wi-Fi network, static address `.166`, original ED25519 SSH host identity,
existing authorized keys plus the host's `id_rsa.pub`, and root SSH access.
Root uses the operator's existing disposable tablet password. Private provisioning
inputs are in `tmp/sl101-nura/deploy/private/`, outside tracked source.
The provisioned image SHA-256 is
`2ee00df2a83dd65dbe2cea8a88a67d1ab7af21825b6f4bd80cac6a5623a4555c`.

Saved Debian boot files, SD partition map and first MiB on the host under
`tmp/sl101-nura/deploy/`. Built a RAM-only rescue root with SSH, Wi-Fi, the current
kernel's modules and card-writing tools; its SSH configuration passed a chroot
check. Loaded the verified current kernel/DTB and rescue initramfs with kexec;
`kexec_loaded` was 1. Requested `systemctl kexec`.

The tablet became unreachable and the RAM rescue's network readiness could not
be established. **No Nura image sectors were written to the SD card.** The
destructive writer requires the rescue marker, exact SD CID, AC, no SD mounts
or swap, and a full image readback hash before expansion. It has not run.
The initial rescue initramfs was 92 MiB; a smaller successor build recipe now
includes only the Broadcom Wi-Fi modules rather than the entire module tree.
Do not assert a size/placement failure without console evidence.

Next: obtain the physical screen state or cold-boot `.166` back into Debian,
then test the smaller rescue and complete the authorized SD write/readback.
eMMC and permanent U-Boot remain outside the write target.


## Rescue console and address diagnosis

The operator confirmed that the second rescue boot reached `/init` and displayed
Wi-Fi output. Its `SD not found` message came from an unquoted semicolon in an
`echo` command, not from an SD probe. The multicast unsupported message was also
present in normal Debian and is not sufficient evidence of a driver regression.
After cold boot, Debian was reachable at `.106`; its SSH host identity and SD CID
matched the persistent-U-Boot target. A third 20 MiB rescue includes association
and SSH logs, a console shell, and a fresh private DTB randomness seed.

During the third rescue attempt, `.166` resolved to MAC `ea:22:bd:fc:ef:76`,
which does not match the tablet's `74:2f:68:74:ff:c8`. A static address conflict
is therefore a concrete network issue. The operator was asked to change the
rescue console address to `.106`; SSH is not yet verified. The offline Nura
profile now uses `.106`. Its updated raw image SHA-256 is
`3b3bc84d50eb369a5941d5e6ef2306f8574a481af2cd28aceb8698b60c64eae0`;
root filesystem read-only e2fsck passed after the change. The corrected compressed
stream is `tmp/sl101-nura/output/sl101-nura-edge-sl101106.img.gz`.
No SD sectors have been written. Next action is obtain rescue logs and verify
RAM-only SSH before streaming this corrected image to the authorized SD target.

## SD write and first Nura boot attempt

The rescue reported its marker, the authorized card CID, AC online, 99% battery,
and no SD mounts before writing. Streamed the `.106` provisioned image to that
SD. The 1,611,661,312-byte readback matched SHA-256
`3b3bc84d50eb369a5941d5e6ef2306f8574a481af2cd28aceb8698b60c64eae0`.
Expanded GPT partition 2 from 1 GiB to 118.6 GiB; `e2fsck -f -p` passed and
`resize2fs` completed. Rebooted from rescue. The tablet MAC returned in ARP at
`.106`, but SSH port 22 is filtered and no Nura runtime evidence is available
remotely yet. Nura hardware boot, Wi-Fi, keyboard, grate and GPU remain pending
physical-console/SSH verification.

## Diagnostic kernel entry on the physical Nura card

The first Nura/grate cold boot remained lit but blank, including another cold
boot. The spare 32 GB Debian card booted successfully on the same tablet at
`.106` (CID `03534453553332478030be3f6400b900`), confirming the recovery route.
Nura's NetworkManager has not been tested at runtime. The failed 128 GB card
was inserted in the host reader: both filesystem UUIDs match the written image;
CID matches except the transport representation of its final end bit.

Installed the verified Debian 6.18.45 kernel/SL101 DTB and matching module tree
onto that Nura card. Default extlinux entry `Nura-known-kernel` uses direct
`root=/dev/mmcblk1p2` with the working Debian console arguments and no initrd.
This isolates Nura userspace/NetworkManager from the grate kernel and initramfs.
The original grate entry remains selectable, with quiet/splash flags removed;
a copy of its original configuration is retained. A local boot hook captures
kernel/network/service state in `/var/log/sl101-boot-diagnostics.log` if Nura
userspace reaches the local runlevel. This entry is diagnostic: the Debian kernel
still lacks the grate staging channel interface required for the GPU work.

## Boot-chain correction after the second blank-screen attempt

The known-kernel SD entry produced the same blank-screen/no-network symptom.
A read-only inspection of the live tablet's internal eMMC at byte 8912896 found
an `ANDROID!` header with `root=/dev/mmcblk1p1 rootfstype=ext4 rootwait rw
console=tty0 video=tegrafb loglevel=7`. Its kernel and appended-DTB hashes exactly
match the running 6.18.45 EC pair. The active SD extlinux path had been assumed
without evidence. Therefore the prior blank attempts do not demonstrate a
runtime failure of the grate kernel or NetworkManager.

The Nura SD's original partition 1 was ext2 boot, whereas the observed boot
arguments expect an ext4 root there. Saved checked archives of the full root
and boot files plus its GPT table under `tmp/sl101-nura/deploy/`. Rebuilt only
this authorized SD as one DOS/MBR Linux partition starting at sector 2048;
restored Nura root to ext4 partition 1, retained its root UUID and the known
kernel's matching modules, moved boot files into `/boot`, removed the old
separate-boot fstab entry, and adjusted the diagnostic extlinux paths/root
argument. Internal eMMC was only read. The restored filesystem passed read-only
e2fsck, restored boot hashes match, and NetworkManager/sshd remain enabled.
Card unmounted; hardware boot on this corrected layout is still pending.

Actual grate-kernel work will require a verified RAM kexec transition from the
working internal-kernel/Nura-root baseline. SD extlinux edits alone must not be
claimed to change the running kernel on this observed boot path.

## Verified Nura runtime and RAM-only grate kernel

The root-on-partition-1 correction cold-booted Nura edge at `.106` using the
internal 6.18.45 kernel. SSH and NetworkManager were running, the expected SD CID
matched, and the static default route was present. The framebuffer and backlight
were both power-blanked (`4`); setting both to `0`, brightness to 100 and selecting
tty1 restored the display. The operator confirmed screen and physical keyboard.
Installed `/etc/local.d/sl101-console-unblank.start` to disable console blanking
and unblank the display at startup. An actual cold-boot check of that hook is
still pending.

Loaded and executed Nura's 7.0.1-postmarketos-grate kernel and SL101 DTB via RAM
kexec with the same root-on-p1 argument. Live SSH confirmed the grate kernel,
`CONFIG_DRM_TEGRA_STAGING=y`, Nura userspace and unblanked display. Its kernel and
DTB SHA-256 are respectively `794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1`
and `01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0`.
Legacy Tegra GR2D class 0x51 and GR3D class 0x60 channel opens and closes passed
(see `tmp/sl101-nura/deploy/grate-channel-proof.txt`). The initial modern-ABI probe
is not counted: this fork's overlapping ioctl 0x50 returns its custom version.
Channels establish the previously missing interface, not rendered GPU output.

Installed labwc/foot/mesa-utils/seatd, and a temporary seatd + pixman labwc probe
survived eight seconds. Temporary processes were stopped afterwards; seatd was
not enabled as a persistent service. Nura-native Mesa 25 Grate build is underway
in isolated pmbootstrap cross-native2 roots with an `/opt/grate-mesa25` prefix.
Debian's glibc-linked Mesa package is unsuitable for Nura's musl userspace.

### Live GLES2 probe (2026-09-30)

Private musl Mesa 25 now initializes GBM/EGL and reports `GL_VENDOR=Grate`,
`GL_RENDERER=Tegra`. Vertex/fragment shaders compile and link. Two missing
Gallium callbacks (stencil reference and blend color) caused NULL calls; local
port changes retain those states without claiming hardware stencil/blend support.
After the second callback fix, triangle submission returns without a GL error,
but centre and corner pixel reads both return zero instead of green/red. The
GPU rendering proof therefore FAILS. Stock Mesa and the user's compositor remain
untouched. Probe source: `tmp/sl101-nura/deploy/grate-render-proof.c`; latest live
trace: `/tmp/grate-render-gdb.log`. Next inspect framebuffer allocation, GR2D
clear/GR3D submission, fence completion and resource readback before enabling this
private driver in labwc. Audio is user-confirmed working; touchscreen calibration
now uses vertical-only `1 0 0 0 -1 1`, awaiting corner confirmation.

### Verified GR2D and GR3D pixels (2026-09-30)

User confirms clean audible stereo ALSA sine test; speaker volume left at 35%.
Bluetooth also user-confirmed. Transient keyboard complaint cleared per user;
no keyboard configuration or driver was changed during GPU tests.

Further port repairs: apply index-bias rejection only to indexed draws; avoid
BO relocations for disabled/absent depth targets; advertise default CPU texture
transfer rather than BLIT. An explicit RGB565 FBO now gives correct red GR2D
clear pixels. With attribute-only position/color shaders (no immediate constants),
GR3D renders a green triangle: 1352 green pixels, 2744 red; center 0,255,0,255,
corner 255,0,0,255. Cleanup completes and `GRATE_RENDER_PROOF_PASSED` prints.
A clean rebuild with debug instrumentation removed reproduced this result live.
Private r2 archive SHA256:
`9998129204311a0a6629ed5a8e3d29135369d47e8bbeaebb3523324851357ab2`.

This establishes actual hardware rendering in the constrained test. Shaders
containing immediate constants still failed the triangle test; vertex compiler
explicitly has a TODO/HACK for immediate uniform storage. EGL window-target
allocation and general accelerated labwc remain unqualified. Continue pixman
for the desktop. Private libs remain confined to `/opt/grate-mesa25`.

### Shader constants and browser (2026-09-30)

Patched vertex immediate recording and uniform upload (high vector slots,
255-index; upload address multiplied by four). Patched fragment MOV immediates
0/1 using hardware zero/one operands; other fragment values are still unsupported.
Guarded empty MFU lists and zero-varying linker setup for constant-color shaders.
Live triangle test now passes with vertex 0/1 immediates and constant-green
fragment shader; centre green, corner red, 1352 green pixels. Patch against the
preexisting local port: `docs/sl101-grate-mesa25-runtime-fixes.patch`.
Private r3 archive SHA256:
`1046d9a0b63319d4004d92cf377f6f33cb834503aa141df48a6f2177d067f969`.

The fragment compiler only implements MOV; general arithmetic, texture handling,
and accelerated desktop remain unfinished. No broad shader support claim.
Firefox startup SIGILL was traced in gdb to `vmov.i32 q8,#0` (NEON), unavailable
on Tegra2. Installed NetSurf 3.11 and launched its GTK3 Wayland frontend on
pixman labwc. Both processes remain alive with no startup errors; visual browser
usability awaits operator confirmation. seatd/labwc were launched for this user
request, without enabling persistent services.
