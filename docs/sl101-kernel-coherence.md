# SL101 kernel artifact coherence — 2026-10-02

## Purpose

This note records the read-only kernel/config/module coherence diagnosis for the
recovered ASUS SL101 and defines the repair gate before any further resume,
zram, nftables, EC/KBC, or Wi-Fi power-management work.

Do not repair individual warnings by blacklisting modules or changing services
until this gate passes.

## Live target identity

Recovered target:

```text
host             sl101-nura
kernel release   6.18.45
boot image       /boot/vmlinuz
vmlinuz sha256   794a3766aed121654aed5b88f3a8d826f38b47fa4fcfb5bb01d3267518a0d9e1
DTB              /boot/tegra20-asus-sl101.dtb
DTB sha256       01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0
```

The recovered tablet is reachable over Wi-Fi/SSH. No device mutation was
performed by this investigation.

## Coherence gate

New host-side tool:

```sh
python scripts/sl101-kernel-coherence.py --root ROOT
python scripts/sl101-kernel-coherence.py --ssh root@HOST
```

It is read-only and checks:

- running kernel release;
- embedded running config from `/proc/config.gz`;
- installed `/boot/config`;
- `/lib/modules/<release>` presence;
- module files and `modules.builtin`;
- explicit ASUS Transformer EC/KBC built-in-vs-loadable conflicts;
- hashes for known SL101 boot image/DTB paths when available.

The JSON schema is:

```text
android-infra.sl101-kernel-coherence.v1
```

Exit status is zero only when the inspected artifact set is coherent.

## Live result

A local snapshot was captured read-only from the live tablet and passed through
the gate. Result:

```text
coherent                 false
gate exit                1
error findings           5
config-symbol differences 3003
```

The five hard failures were:

1. `kernel_config_mismatch`;
2. built-in ASUS EC has stale loadable module file;
3. ASUS EC missing from installed `modules.builtin`;
4. built-in ASUS EC keyboard has stale loadable module file;
5. ASUS EC keyboard missing from installed `modules.builtin`.

### EC/KBC proof

The running kernel says:

```text
CONFIG_MFD_ASUS_TRANSFORMER_EC=y
CONFIG_SERIO_ASUS_TRANSFORMER_EC=y
```

The EC itself initializes successfully very early:

```text
0.863 s  Model         : ASUS-EP102-DOCK
0.868 s  FW version    : SL101-0202
0.873 s  Config format : ECFG-0001
0.878 s  HW version    : PCBA-EP102
1.070 s  AT Raw Set 2 keyboard registered
```

But the installed module tree also contains:

```text
/lib/modules/6.18.45/kernel/drivers/mfd/asus-transformer-ec.ko
/lib/modules/6.18.45/kernel/drivers/input/serio/asus-transformer-ec-kbc.ko
```

and `modules.builtin` identifies neither driver.

Later userspace therefore attempts to load code that is already built into the
kernel:

```text
22.538 s  asus_transformer_ec: exports duplicate symbol asus_dockram_access_ctl
22.962 s  Driver 'asus-transformer-ec-kbc' is already registered
```

This is an artifact-set consistency defect, not evidence that the SL101 EC
failed to probe.

Do not "fix" it by blacklisting the two modules. That would hide the symptom
while leaving the rest of the kernel/config/module set untrusted.

## zram and nftables are explained by the same split

The embedded running config versus installed `/boot/config` says:

```text
CONFIG_ZRAM:
  runtime = n
  /boot/config = y

CONFIG_ZSMALLOC:
  runtime = <missing>
  /boot/config = y

CONFIG_NETFILTER:
  runtime = n
  /boot/config = y

CONFIG_NETFILTER_NETLINK:
  runtime = <missing>
  /boot/config = m

CONFIG_NF_TABLES:
  runtime = <missing>
  /boot/config = m
```

There are no matching zram, nf_tables, or nfnetlink module files in the current
module tree.

Therefore:

- the failed zram service is expected with the running kernel;
- nftables cannot work with this running kernel;
- neither should be debugged as an independent OpenRC/service problem until the
  kernel artifact set is repaired.

## Wi-Fi result

The live running config says:

```text
CONFIG_CFG80211=y
CONFIG_BRCMFMAC=m
CONFIG_BRCMFMAC_SDIO=y
```

while `/boot/config` says `CONFIG_CFG80211=m`.

BCM4329 SDIO itself enumerates and the generic firmware successfully runs:

```text
mmc2: new SDIO card at address 0001
brcmfmac: using brcm/brcmfmac4329-sdio for BCM4329/3
Firmware: BCM4329/3 wl0 ... version 4.220.48
```

The board-specific firmware request falls back to the generic BCM4329 image,
and the missing CLM blob is logged. Those warnings should be cleaned later, but
they are not the first repair target while kernel/config/module coherence is
failing.

Resume qualification should specifically verify the SDIO keep-power/resume
path only after a coherent kernel set boots.

## maXTouch / keyboard warnings

maXTouch reports a missing `maxtouch.cfg` but still probes the touchscreen with
the correct 1279x799 geometry and creates an input device. This is cleanup work,
not the primary boot/resume blocker.

The early keyboard reset warning also occurs after the EC/KBC path has already
registered the keyboard. Re-evaluate it only after stale EC/KBC module loading
has disappeared.

## Safe repair order

### 1. Preserve the known bootable state

Before replacing anything, record hashes/copies of:

- current boot image;
- current DTB;
- current embedded runtime config;
- current `/boot/config`;
- current `/lib/modules/6.18.45` metadata/tree.

Do not overwrite the only known bootable entry.

### 2. Produce one coherent kernel artifact set

One build must supply all of:

```text
kernel image
exact build .config -> installed /boot/config
matching SL101 DTB
matching /lib/modules/<release>
matching modules.builtin/modules.dep metadata
```

Do not combine an image from one build with config/modules from another build,
even when `uname -r` strings are identical.

Prefer a distinct release/localversion while qualifying, so an old and a new
module tree cannot collide under the same `/lib/modules/6.18.45` directory.

### 3. Stage as an alternate boot candidate

Install the coherent set to a new/non-default boot entry first. Keep the current
known recovery/default path intact.

A human must be physically present for the first boot.

### 4. Run the coherence gate immediately after boot

Expected result:

```text
coherent=true
config_difference_count=0
no builtin_has_stale_module_file
no builtin_metadata_mismatch
```

Also verify the boot image/DTB hashes match the candidate manifest.

### 5. Re-check boot log

The following current warnings must disappear before resume qualification:

```text
asus_transformer_ec: exports duplicate symbol ...
Driver 'asus-transformer-ec-kbc' is already registered
```

### 6. Re-enable features according to the actual coherent config

Only now decide whether the candidate kernel should have:

- zram;
- nftables;
- cfg80211/brcmfmac built-in vs modules;
- EC/KBC built-in vs modules.

Then enable/test the corresponding OpenRC services.

### 7. Resume work remains shallow-first

After artifact coherence and normal boot/input/network qualification:

1. `loginctl --dry-run suspend`;
2. inhibitor-aware, human-present `freeze`;
3. verify display, EC/keyboard, touchscreen, Wi-Fi, labwc/NuraLoumi and network;
4. only then consider a separately authorized deep-suspend experiment.

Do not use unattended `rtcwake -m mem` as a shortcut.

## Acceptance before calling the kernel repaired

- coherence gate passes;
- no duplicate EC/KBC module load;
- keyboard and touchscreen remain present;
- Wi-Fi connects normally;
- zram/nftables state matches the **running embedded config**;
- clean reboot evidence is captured;
- pixman desktop remains the default recovery path;
- no deep suspend is attempted during artifact-coherence repair.
