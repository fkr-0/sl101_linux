# ASUS SL101 EC / keyboard test report

Date: 2026-09-21

Device: ASUS Eee Pad Slider SL101

Kernel baseline: Linux 6.18.45, ARMv7

Userspace: Debian Trixie armhf

## EC identification

```text
Model         : ASUS-EP102-DOCK
FW version    : SL101-0202
Config format : ECFG-0001
HW version    : PCBA-EP102
```

Runtime bus:

- EC: I2C `0x19`
- DockRAM: I2C `0x1b`
- live adapter: `i2c-5`

## Initial result with v10-style EC support

The MFD driver probed successfully and created the KBC serio child.

Linux exposed:

```text
N: Name="AT Raw Set 2 keyboard"
P: Phys=i2c-5-0019/serio0/input0
H: Handlers=sysrq kbd leds event3
```

but `atkbd` failed initialization:

```text
atkbd serio0: keyboard reset failed on i2c-5-0019/serio0
atkbd serio0: Failed to deactivate keyboard
atkbd serio0: Failed to enable keyboard
```

## Downstream comparison

ASUS's downstream SL101/Transformer EC driver reads event register `0x6a`
with an 8-byte SMBus I2C block read.

The v10 MFD series reads `ASUSEC_ENTRY_SIZE` (32) bytes in its clear-buffer
and interrupt paths.

## Instrumented packet evidence

Observed SL101 keyboard reset response:

```text
03 09 fa aa
```

Interpretation:

- `03`: three following bytes
- `09`: EC status
- `fa`: PS/2 ACK
- `aa`: keyboard BAT success

Some command ACK packets are valid OBF packets without KEY/KBC set.

## Working changes

1. Read SL101 EC events with 8-byte transactions at `0x6a`.
2. Send valid non-AUX, non-SMI/SCI OBF packets to keyboard serio0.
3. Interpret `data[0]` as the number of following bytes and forward
   `data[0] - 1` payload bytes after skipping count + status.

## Validation method

The persistent boot artifacts were kept untouched.

Known-good baseline:

```text
/boot/zImage
sha256 aaf847d5a15a5c673d921f87c3c08d45dd7ddff8185723dd7da804289265d630

/boot/tegra20-asus-sl101.dtb
sha256 7c938df062396a142f800c3807ba0d8f4255cd9ff8bfc8d09e83ee93b1dcb52a
```

The experimental kernel and DTB were staged under `/tmp`, verified by
SHA-256 and loaded with:

```sh
kexec -l /tmp/sl101-kbd-zImage \
    --dtb=/tmp/sl101-kbd.dtb \
    --command-line="$(cat /proc/cmdline)"
```

Then executed with:

```sh
sync
kexec -e
```

Immediately before the successful test the battery reported Charging at 52%
with approximately +765 mA current.

## Result

PASS: the built-in physical SL101 sliding keyboard works after the three
changes above.

On a later SSH inspection of the working kernel, Linux still exposed
`AT Raw Set 2 keyboard` at `i2c-5-0019/serio0/input0`, and the boot log had no
serio0 reset/deactivate/enable failure. The remaining
`atkbd serio1: keyboard reset failed on i2c-5-0019/serio1` message refers to
the secondary PS/2 port, not the working built-in keyboard path.

No persistent boot-path overwrite was required for validation.

## Cleaned upstream-form verification

After the hardware PASS, temporary diagnostic logging was removed and the
8-byte event-read quirk was restricted to the physically verified SL101
variant. The cleaned source was then force-compiled for:

- `drivers/mfd/asus-transformer-ec.o`
- `drivers/input/serio/asus-transformer-ec-kbc.o`
- `nvidia/tegra20-asus-sl101.dtb`

using the pinned Debian cross-build container and `-j1`. All three targets
built successfully. The cleaned DTB SHA-256 is:

```text
7533523688c510723064187167076ec5261ca0248e66860b01596f65706c426b
```

The exact cleaned build has not yet received a second hardware reboot; the
physical PASS above refers to the diagnostic build with the same SL101
functional protocol changes.

## Second-device verification (cleaned upstream build)

Date: 2026-09-21

A second ASUS SL101 (recovered from TWRP bootloop via fusée/APX → U-Boot
→ SD card) was booted with the cleaned upstream kernel and DTB:

```text
zImage-ec-current
sha256 ab170625dbe038965d3c91a684e9153a91ad0e590edcd47c275c1ff3a7495766

tegra20-asus-sl101-ec-current.dtb
sha256 7533523688c510723064187167076ec5261ca0248e66860b01596f65706c426b
```

Boot path: fusée → patched U-Boot (bootdelay=3) → SD card extlinux →
kexec to EC kernel. SSH at `192.168.23.166`.

### EC identification (second device)

```text
Model         : ASUS-EP102-DOCK
FW version    : SL101-0202
```

Same EC model/firmware as the first device.

### Keyboard test matrix

| Test                         | Result | Evidence                                         |
|------------------------------|--------|--------------------------------------------------|
| EC probe + serio0 register   | PASS   | No reset/deactivate/enable errors in dmesg       |
| Ordinary keys (letters)      | PASS   | A–Z all verified via evtest                      |
| Number row (0–9)             | PASS   | All digits + MINUS, EQUAL                        |
| Enter / Backspace            | PASS   | Multiple press/release cycles                    |
| Tab                          | PASS   | KEY_TAB captured                                 |
| Left Shift                   | PASS   | value 1→2 (autorepeat)→0 with held combos        |
| Right Shift                  | PASS   | KEY_RIGHTSHIFT press/release                     |
| Left Ctrl                    | PASS   | 20 press/release pairs captured                  |
| Left Alt                     | PASS   | KEY_LEFTALT press/release                        |
| Right Alt                    | PASS   | KEY_RIGHTALT press/release, combo with R          |
| Caps Lock + LED              | PASS   | KEY_CAPSLOCK + LED_CAPSL toggle                  |
| Key repeat                   | PASS   | REP_DELAY=250, REP_PERIOD=33, autorepeat seen    |
| Arrow keys                   | PASS   | KEY_UP (6 presses), KEY_PAGEDOWN (3 presses)     |
| Brackets                     | PASS   | KEY_LEFTBRACE, KEY_RIGHTBRACE                    |
| Grave / tilde                | PASS   | KEY_GRAVE                                        |
| Space                        | PASS   | KEY_SPACE press/release                          |

### Slider mode switch

```text
Event: type 5 (EV_SW), code 1 (SW_TABLET_MODE), value 1  (closed)
Event: type 5 (EV_SW), code 1 (SW_TABLET_MODE), value 0  (open)
```

Toggled twice. extcon-keys at `/dev/input/event3` correctly reports slider
open/close state.

### Suspend / resume

```text
PM: suspend entry (deep)
Entering suspend state LP1
CPU1 is up
PM: suspend exit
```

`rtcwake -m mem -s 5` entered LP1 deep suspend, resumed cleanly.
Keyboard worked normally after resume. Display and backlight returned
(brightness 248). Minor accelerometer resume error (kxcjk1013, unrelated
to keyboard).

### Battery telemetry

```text
status      : Discharging
capacity    : 88%
temp        : 27.7°C
cycle_count : 83
charge_now  : 1776 mAh
model       : EP10222
manufactured: 2011-08-05
```

AC adapter detected (`online: 1`). Full SBS battery interface functional
via `sbs-5-000b`.

### Conclusion

PASS: the cleaned upstream-form kernel works on two independent SL101
devices. The three protocol fixes (8-byte event reads, OBF routing,
data[0]-1 payload count) are confirmed necessary and sufficient for
full keyboard functionality.
