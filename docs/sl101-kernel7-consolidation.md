# Nura 7.x kernel consolidation — 2026-10-02

## Decision

Nura's canonical kernel baseline is now:

```text
linux-postmarketos-grate 7.0.1-r4
kernel release: 7.0.1-postmarketos-grate
source commit: bfffc6d6656e87f3de3aa4c09d852849081ef088
```

The 6.18.45 line is retained as recovery/reference evidence. The host-only
`6.18.45-sl101-coherent-r1` build remains useful for the coherence tooling and
for comparison against the newer Transformer-EC implementation, but it is no
longer the primary Nura deployment track.

Do not create a `7.0.1-nura-r1` release string merely for repackaging. Keep the
exact stock release while contents are identical. Introduce a Nura-specific
release namespace only when kernel/config/DTB/module contents intentionally
diverge.

## Why 7.x is the canonical baseline

The exact 7.0.1 package has already run repeatedly on the physical SL101 via
RAM kexec with the Nura userspace.

Archived evidence establishes:

- NetworkManager + SSH on Nura;
- labwc with the pixman renderer;
- NuraLoumi running on the tablet;
- legacy Grate channel access;
- real GR2D clear pixels;
- real GR3D triangle pixels;
- BCM4329/brcmfmac operation;
- SL101 EC identification and keyboard registration.

This is substantially more useful as the canonical runtime baseline than the
mixed 6.18 cold-boot state.

## Exact baseline artifact set

Package:

```text
tmp/sl101-nura/work/cache_apk_armv7/
  linux-postmarketos-grate-7.0.1-r4.bd607950.apk

sha256
d0e00bacddd21a2aaa2a116f9a3bf199a01a73b117d5f13e449b37f08094bdb1
```

Installed Nura rootfs artifacts:

```text
vmlinuz
794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1

config
6b09863a5f4356ce615f7d5d4cdecbba4cd2cc208c34125954af9534648f9248

tegra20-asus-sl101.dtb
01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0

modules.builtin
3cfc5b6144880d039cca360bfd721b922e6ce3de02564c0074b334c2da5064c8

modules.dep
1aa4f4e7f50840eda7b660b041836e332b72bf90a543f51de67a152d8b98c0fb

modules.alias
73e68a79ed2d8dbc709cd4ff3a8883d60bc20316819873d25b7a316e20d0cd78
```

The module tree contains 587 loadable modules. A full per-file SHA-256 manifest
is retained under:

```text
tmp/sl101-nura/kernel7-consolidation/modules.sha256
```

The complete consolidation provenance and manifest are:

```text
tmp/sl101-nura/kernel7-consolidation/provenance.json
sha256 099d002939b39f8177033ef110a18b39c302a9c51371a9e3df3b75cc94c208e3

tmp/sl101-nura/kernel7-consolidation/MANIFEST.sha256
sha256 91a38156b45e5197bbb9b22367d005dfbc1b610180272d1b5e0cf2d9a917d66d
```

## Coherence result

The exact package/rootfs set was projected into the same synthetic-root format
used by `scripts/sl101-kernel-coherence.py`.

Result:

```text
coherent=true
errors=0
config_difference_count=0
module_count=587
```

This is the invariant that future Nura kernel releases must preserve.

The previous 6.18 cold-boot state failed this same gate with 3003 config
differences plus stale EC/KBC module conflicts. Do not reintroduce that class of
composition error.

## Grate / GPU baseline

The package config contains:

```text
CONFIG_STAGING=y
CONFIG_DRM_TEGRA_STAGING=y
```

The package's `modules.builtin` identifies:

```text
kernel/drivers/gpu/host1x-grate/host1x-drv.ko
kernel/drivers/gpu/drm/grate/tegra-drm.ko
```

These are built into the kernel image rather than supplied as separate module
files.

Real-device GR2D and GR3D pixel proof has already been archived for this kernel
release. This does not imply the current private Mesa texture/EGL work is
complete; those GPU acceptance lanes remain separate.

## Memory / firewall policy

Unlike the recovered 6.18 running kernel, the canonical 7.x config already has:

```text
CONFIG_ZRAM=y
CONFIG_ZSMALLOC=y

CONFIG_NETFILTER=y
CONFIG_NETFILTER_NETLINK=m
CONFIG_NF_TABLES=m
```

Therefore the earlier failed zram/nftables services should not be "repaired"
against the 6.18 runtime. Their canonical qualification belongs on 7.x.

## Wi-Fi policy

The 7.x baseline contains:

```text
CONFIG_CFG80211=m
CONFIG_BRCMFMAC=m
CONFIG_BRCMFMAC_SDIO=y
```

Critical module hashes:

```text
brcmfmac.ko.zst
7dfb787caf9cd86bcdc0b1737ba0427c6bcd2992fdcf779cfbd463765b0fff11

cfg80211.ko.zst
205905304261152e67cabc5ccaa7add1edf1bb22ecfb94345d163db3a1964dcb
```

The SL101 DTB already has the SDIO keep-power-in-suspend property, so missing
that property is not the explanation for the failed deep-resume experiment.

Do not run another deep-suspend experiment until persistent 7.x boot and shallow
freeze/resume have both been qualified with a human present.

## EC/KBC R1 policy

Canonical R1 deliberately retains the existing Grate ASUS EC driver family:

```text
kernel/drivers/mfd/asus-ec.ko.zst
sha256 407a47f94b483a00f19435abf1ec54372c7a190eed07b1a0ec9ce2ea27379f31

kernel/drivers/input/serio/asus-ec-kbc.ko.zst
sha256 d14abffcc5f04e6f8b689232c2e091bb5e88e819ca0fc9b8afd9dbb91a7773a1

kernel/drivers/input/keyboard/asus-ec-keys.ko.zst
sha256 a6a2a437a176c6020d1f104dc1ad88ac4fcf17a9456f1bfcdbc0a57ebc31c4c9
```

This choice is evidence-based rather than an endorsement of the older API.
Archived 7.x hardware dmesg shows:

```text
asus-ec 5-0019: model         : ASUS-EP102-DOCK
asus-ec 5-0019: FW version    : SL101-0202
asus-ec 5-0019: Config format : ECFG-0001
asus-ec 5-0019: HW version    : PCBA-EP102
input: AT Raw Set 2 keyboard ...
```

Evidence file SHA-256:

```text
22bb5681acb8a73ea642b9afa78a1215081a095cbb41af4e1165d2cab5ceac7b
```

The recurring secondary warning remains:

```text
atkbd serio1: keyboard reset failed on i2c-5-0019/serio1
```

No 6.18-style duplicate-symbol or duplicate-driver collision appears in this
archived 7.x boot evidence.

Therefore EC modernization is a **separate kernel-change lane**, not a blocker
for R1 consolidation.

## Relationship to the newer Transformer-EC work

The 6.18 SL101 work uses the newer Transformer-EC implementation and a newer
SL101-specific DT representation. That work remains valuable.

Do not mix those files opportunistically into the stock 7.0.1 package.

If the newer EC implementation is brought forward, create a distinct release
such as:

```text
7.0.1-nura-r1
```

and require all of these to come from the same build:

```text
kernel image
embedded config
installed /boot/config
SL101 DTB
/lib/modules/<exact-release>
modules.builtin / modules.dep / modules.alias
```

Then rerun the coherence gate before any hardware boot.

## Consolidation phases

### Phase A — exact stock 7.0.1 baseline

Status: **host-qualified and previously hardware-exercised via RAM kexec**.

Use the exact package artifacts above without kernel modifications.

Next hardware gate:

1. preserve the current known recovery path;
2. stage the exact 7.0.1 artifact set as a non-default persistent candidate;
3. human physically present for first boot;
4. verify exact release, image/DTB/module hashes;
5. run the coherence gate;
6. verify display/backlight;
7. verify touchscreen;
8. verify slider keyboard;
9. verify Wi-Fi/SSH;
10. verify zram;
11. verify nftables;
12. start labwc with pixman;
13. start NuraLoumi;
14. perform a clean reboot and record boot timing.

No deep suspend in this phase.

### Phase B — shallow resume qualification

Only after Phase A passes:

1. `loginctl --dry-run suspend`;
2. constrain suspend to shallow `freeze`;
3. human-present suspend/wake;
4. verify display, EC/KBC, touch, Wi-Fi, labwc/NuraLoumi and providers;
5. record network recovery timing.

Deep sleep remains separately authorized.

### Phase C — EC modernization

Evaluate forward-porting the newer Transformer-EC/SL101-specific DT work onto
the Grate kernel.

Do this only if it provides a concrete improvement over the proven R1 legacy
stack, such as:

- removing the secondary serio warning;
- better slider/dock event semantics;
- better suspend/resume behavior;
- cleaner upstream alignment.

Any such change requires a new Nura-specific release namespace and a fresh
coherent artifact set.

### Phase D — GPU promotion

Keep the current Grate Mesa/EGL/TEX lanes independent from kernel consolidation.
The default desktop remains pixman until texture, arithmetic, EGL window,
compositor endurance and no-fault qualification all pass.

## 6.18 disposition

Keep:

- the known recovery information;
- the host-only `6.18.45-sl101-coherent-r1` artifact;
- the Transformer-EC source/DT lessons;
- the coherence diagnosis.

Do not spend additional release-engineering effort trying to make 6.18 the main
Nura runtime unless 7.x develops a regression that cannot be resolved.

## Invariant for every future Nura kernel

A candidate is not boot-qualified unless:

```text
uname release == module directory release
embedded runtime config == installed /boot/config
image + DTB + config + modules come from one build/package
module metadata matches module files
no duplicate built-in/loadable driver implementation
manifest hashes verify
```

The kernel coherence gate is authoritative for this artifact-level invariant.
