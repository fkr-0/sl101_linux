# SL101 ASUS Transformer EC upstream preparation

Prepared from real-hardware validation on an ASUS Eee Pad Slider SL101.

## Upstream state

The newest public ASUS Transformer EC series found as of 2026-09-21 is:

- `[PATCH v10 0/7] mfd: Add support for Asus Transformer embedded controller`
- posted by Svyatoslav Ryhel on 2026-07-21
- public thread: https://patchew.org/linux/20260721095233.420823-1-clamor95%40gmail.com/
- v10 patch 2/7 (MFD): https://lkml.iu.edu/2607.2/09834.html
- v10 patch 3/7 (serio/KBC): https://lkml.iu.edu/2607.2/09831.html

The series already contains the `asus,sl101-ec-dock` compatible and an SL101 MFD cell composition, so this work should be contributed as corrections to that series rather than as a competing driver.

## Real SL101 evidence

Hardware / firmware observed:

- model: `ASUS-EP102-DOCK`
- firmware: `SL101-0202`
- config format: `ECFG-0001`
- hardware: `PCBA-EP102`
- EC I2C address: `0x19`
- DockRAM address: `0x1b`
- AP_WAKE: Tegra GPIO S2, active-low level IRQ
- EC_REQUEST: Tegra GPIO S3, active-low
- EC event register: `0x6a`
- downstream ASUS SL101 driver reads this event register in 8-byte transactions
- observed reset event: `03 09 fa aa`
  - `03`: three bytes follow the count byte
  - `09`: OBF + KBC status
  - `fa`: PS/2 ACK
  - `aa`: PS/2 BAT success

The v10 series failed on the physical SL101 with `atkbd` reset/deactivate/enable errors. A kernel containing the changes represented by the two fixup diffs below boots through RAM-only kexec and the physical sliding keyboard works.

## Recommended upstream shape

Do **not** send these as a competing replacement for the v10 series.

1. Send the MFD finding as a reply/fixup for v10 patch 2/7:
   - `v10-2-mfd-sl101-8-byte-events.diff`

2. Send the serio finding as a reply/fixup for v10 patch 3/7:
   - `v10-3-serio-fix-keyboard-responses.diff`

3. Offer the hardware result / Tested-by line in the thread:
   - `v10-reply-draft.txt`
   - `test-report.md`

4. After the EC binding/driver is accepted, submit the board description separately to the Tegra maintainers:
   - `arm-dts-tegra20-asus-sl101-add-ec.patch`

The DTS patch depends on the binding that introduces `asus,sl101-ec-dock`.

## Why the serio change is not just an SL101 guess

v9 of the posted serio driver used `n = data[0] - 1`. v10 tightened the upper bound to address a possible out-of-buffer read but also changed the payload count to `data[0] - 2`.

The real SL101 packet `03 09 fa aa` proves that the count byte describes the number of following bytes. After skipping count + status, two payload bytes remain. The v10 expression forwards only `fa`, dropping the BAT byte `aa`.

The prepared diff keeps the v10 bound and restores `n = data[0] - 1`.

The same patch also accepts a valid non-AUX OBF packet as keyboard data. ASUS's downstream driver does this when polling keyboard command responses, and it is required for ACK-only status packets that do not set KEY/KBC.

## Preparation verification

- all three prepared patch files dry-apply cleanly to their intended reconstructed baselines;
- `scripts/checkpatch.pl --no-tree --no-signoff` reports 0 errors and 0 warnings for each patch;
- the cleaned MFD object, KBC serio object and SL101 DTB were force-rebuilt with the pinned armhf cross-toolchain container at `-j1`;
- the rebuilt DTB SHA-256 is `7533523688c510723064187167076ec5261ca0248e66860b01596f65706c426b`.

A full highly-parallel container rebuild was also attempted, but the bind-mounted build tree intermittently lost compiler dependency files under high `-j` concurrency (`fixdep: error opening ... .d`). That is an unrelated build-environment race; the touched objects and DTB compile cleanly when forced and serialized.

The physical keyboard PASS was obtained with the diagnostic build implementing the same SL101 functional changes. The final cleaned source removes debug logging and limits the 8-byte quirk to the physically verified SL101; that cleaned form has been compile-verified but has not yet been separately rebooted on the tablet.

## Before sending

The files intentionally do not invent the operator's legal identity or DCO sign-off.

Before mailing:

- rebase/fold the changes onto the maintainer's latest branch or v11 if one appears;
- add your real `Signed-off-by:` with `git commit -s`;
- add a real `Tested-by:` identity if desired;
- run `scripts/checkpatch.pl`;
- rebuild the affected ARM kernel/DTB;
- repeat a cold boot or kexec hardware test;
- re-run `scripts/get_maintainer.pl` on the final commits.

Likely EC-series recipients from the current thread include Svyatoslav Ryhel, Michał Mirosław, Ion Agorria, Lee Jones and Dmitry Torokhov, with `linux-input@vger.kernel.org` and `linux-kernel@vger.kernel.org`. Use the final series' own recipient list rather than hard-coding stale addresses.

The DTS patch should be routed through the Tegra maintainers and `linux-tegra@vger.kernel.org`.
