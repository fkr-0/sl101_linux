# SL101 ASUS Transformer EC upstream submission checklist

## Current upstream target

As of 2026-09-21, the newest public series found is:

- `[PATCH v10 0/7] mfd: Add support for Asus Transformer embedded controller`
- author: Svyatoslav Ryhel
- cover Message-ID: `20260721095233.420823-1-clamor95@gmail.com`
- Patchew: https://patchew.org/linux/20260721095233.420823-1-clamor95%40gmail.com/

Re-check for v11+ immediately before sending.

## What to send

### EC series feedback/fixups

Send these as replies/fixups to the active v10 thread so they can be folded into the next revision:

- `v10-2-mfd-sl101-8-byte-events.diff`
- `v10-3-serio-fix-keyboard-responses.diff`
- `fixup-cover-letter.txt`
- optionally include `test-report.md` as supporting evidence, or summarize it in the mail body

Do not present this as a competing EC driver series.

### Tegra board description

Keep this separate:

- `arm-dts-tegra20-asus-sl101-add-ec.patch`

It depends on the EC binding/driver introducing `asus,sl101-ec-dock`.

Route the final DTS patch using the output of:

```sh
scripts/get_maintainer.pl arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dts
```

The current tree identifies the Tegra maintainers and `linux-tegra@vger.kernel.org`; use fresh output at send time.

## Required identity step

The prepared files intentionally contain no fabricated DCO identity.

Before sending:

1. configure the real submission identity in Git;
2. add a real `Signed-off-by: Name <email>` to each patch that you submit as a patch;
3. optionally add a real `Tested-by: Name <email>` to the maintainer's v10 series/reply;
4. do not use the placeholder name from the cover letter.

The DCO sign-off is a legal attestation, so it must be provided by the submitter.

## Final technical gate

Before mail submission:

- [x] confirm no newer v11+ series exists (checked 2026-09-21, v10 is latest)
- [x] boot the exact cleaned debug-free zImage once on the SL101
- [x] confirm EC model/firmware detection (ASUS-EP102-DOCK / SL101-0202, two devices)
- [x] confirm keyboard serio0 registers without reset/enable errors
- [x] test ordinary keys (A–Z, 0–9, punctuation, brackets, grave)
- [x] test Shift/Ctrl/Alt (LeftShift, RightShift, LeftCtrl, LeftAlt, RightAlt all captured)
- [x] test key repeat (REP_DELAY=250, REP_PERIOD=33, autorepeat value 2 seen)
- [x] test at least a few extended/special keys (arrows, PageDown, CapsLock+LED, Space, Tab)
- [x] exercise slider/tablet-mode switch (SW_TABLET_MODE toggled twice on second device)
- [x] perform one suspend/resume cycle if stable enough (LP1 deep, rtcwake 5s, clean resume)
- [x] confirm display returns (backlight 248 after resume)
- [x] confirm charging/battery telemetry remains sane (88%, 27.7°C, SBS interface working)
- [x] verify persistent known-good extlinux entry remains available
- [x] run `scripts/checkpatch.pl` on the final mail patches (0 errors, 0 warnings)
- [x] run `scripts/get_maintainer.pl` on the final patches
- [x] add DCO sign-offs (Florian Krischer <florian.krischer@fkr.dev>)
- [x] use `git send-email --dry-run` before the real send

## Threading

The v10 cover Message-ID is:

```text
20260721095233.420823-1-clamor95@gmail.com
```

For a general test report or fixup cover note, reply to the v10 cover thread.

For individual fixups, prefer replying to the corresponding v10 patch 2/7 or 3/7 mail if the exact Message-ID is available from the downloaded mbox/lore archive. If not, replying to the cover thread is still preferable to starting an unrelated thread.

## Suggested subject lines

```text
[PATCH v10 fixup 0/2] ASUS Transformer EC: SL101 keyboard event/response fixes
[PATCH v10 fixup 1/2] mfd: asus-transformer-ec: use 8-byte event reads on SL101
[PATCH v10 fixup 2/2] input: serio: asus-transformer-ec: fix keyboard response framing
```

For the later board patch:

```text
[PATCH] ARM: tegra: Add embedded controller to ASUS SL101
```

## Evidence already collected

Physical device:

```text
Model         : ASUS-EP102-DOCK
FW version    : SL101-0202
Config format : ECFG-0001
HW version    : PCBA-EP102
```

Observed reset response:

```text
03 09 fa aa
```

Known-good persistent boot artifacts during kexec development:

```text
/boot/zImage
aaf847d5a15a5c673d921f87c3c08d45dd7ddff8185723dd7da804289265d630

/boot/tegra20-asus-sl101.dtb
7c938df062396a142f800c3807ba0d8f4255cd9ff8bfc8d09e83ee93b1dcb52a
```

Cleaned DTB build:

```text
7533523688c510723064187167076ec5261ca0248e66860b01596f65706c426b
```

The physical keyboard PASS was first obtained using a diagnostic build containing the same functional protocol fixes.

Second device (cleaned upstream build, 2026-09-21):

```text
zImage-ec-current
sha256 ab170625dbe038965d3c91a684e9153a91ad0e590edcd47c275c1ff3a7495766

tegra20-asus-sl101-ec-current.dtb
sha256 7533523688c510723064187167076ec5261ca0248e66860b01596f65706c426b
```

Boot path: fusée → U-Boot (patched bootdelay=3) → SD card extlinux → kexec.
Full keyboard test matrix passed. Suspend/resume (LP1 deep) passed.
Battery/AC telemetry functional. SW_TABLET_MODE slider switch verified.

All technical gates passed on two independent SL101 devices. The only
remaining pre-send gate is confirming no v11+ series exists.
