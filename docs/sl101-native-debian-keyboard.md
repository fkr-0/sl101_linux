# Resurrecting the ASUS Eee Pad Slider SL101: Native Debian, Mainline Linux, and the Keyboard Fix

The ASUS Eee Pad Slider SL101 is a wonderfully odd machine to bring back in 2026. It is a Tegra 2 tablet from the Android 3.x era with a built-in sliding keyboard, a proprietary ASUS embedded controller, and just enough similarity to the better-known Transformer TF101 to send you down the wrong path if you assume they are identical.

This is the story of taking one from “we can boot Linux” to a genuinely usable native Debian system — including the point where everything worked except the keyboard, the safe kexec loop we used to debug it, and the small protocol details we found while validating the modern ASUS Transformer EC patch series on real SL101 hardware.

The short version is that the keyboard was never a Tegra matrix-keyboard problem. It lives behind the ASUS/Nuvoton embedded controller. Once we described that EC correctly in the device tree, the modern driver could probe it, but the SL101 exposed two assumptions that prevented `atkbd` from completing PS/2 initialization: the EC event window is eight bytes, not 32, and keyboard command replies do not always carry the KEY/KBC status bits. A third v10 framing regression dropped the final byte of packets such as the keyboard reset ACK/BAT response.

Fix those three details and the keyboard works.

## What “native Debian” means here

This project originally started with a RootBind-first mindset because that was the safest way to reuse an old Android-era tablet without immediately replacing its entire boot chain.

The system we ended up debugging, however, is not Debian in a chroot and it is not Linux userspace running on an Android kernel.

Once the machine boots, the stack is:

```text
U-Boot / extlinux
        |
        +-- Linux 6.18.45 zImage
        +-- tegra20-asus-sl101.dtb
        |
        +-- Debian Trixie armhf root filesystem
             on /dev/mmcblk1p1
```

Android is not the runtime layer. The kernel is a native ARM Linux kernel, PID 1 is Debian's systemd, and the hardware is driven by normal Linux subsystems such as DRM, I2C, serio, `atkbd`, SBS battery and brcmfmac.

So I would describe the result as **native Debian on the SL101, reached through the boot/recovery work that began as the RootBind port**.

It is also not postmarketOS. postmarketOS is a separate Alpine-based distribution and packaging ecosystem. The hardware work here is useful to postmarketOS, but the running userspace in this project is Debian Trixie armhf.

## 1. Start with a reproducible kernel and rootfs

Before touching the physical tablet we built a reproducible host-side baseline.

The kernel was pinned to Linux 6.18.45, commit:

```text
bf3be28f6721e24961992ebb9e61c0cf21a56806
```

That matters because Linux 6.18 is the first mainline release family containing an SL101-specific device tree. The SL101 support was developed in the Tegra tree and tested on real hardware before being merged for 6.18.

The userspace was Debian Trixie armhf, bootstrapped on an x86_64 workstation in a pinned Debian build container.

The build process produced four things that always had to stay together:

1. the kernel `zImage`;
2. `tegra20-asus-sl101.dtb`;
3. the matching `/lib/modules/<kernel-release>` tree;
4. the Debian armhf root filesystem.

The kernel was built with the normal ARM hard-float GNU cross toolchain. In our isolated build container the basic pattern was:

```sh
make -C /workspace/linux \
    O=/workspace/build \
    ARCH=arm \
    CROSS_COMPILE=arm-linux-gnueabihf- \
    multi_v7_defconfig

make -C /workspace/linux \
    O=/workspace/build \
    ARCH=arm \
    CROSS_COMPILE=arm-linux-gnueabihf- \
    -j8 zImage dtbs modules
```

For every test build we kept the source tree and build tree separate. That made it easy to preserve a known-good kernel while producing experimental kernels next to it.

## 2. Boot the already-flashable SL101 with extlinux

I am deliberately starting this article at the point where the tablet can already boot U-Boot/Linux.

Current upstream U-Boot has an SL101 configuration and an SL101-aware recovery/install path, but its permanent installation procedure replaces the vendor ASUS bootloader and erases/repartitions eMMC. That is a separate recovery-sensitive operation and should be followed from current U-Boot documentation rather than copied from an old TF101 guide.

Once U-Boot is available, the Linux side is pleasantly conventional.

Our normal boot files were:

```text
/boot/zImage
/boot/tegra20-asus-sl101.dtb
/boot/extlinux/extlinux.conf
```

The working extlinux entry was:

```text
default Debian
timeout 30

label Debian
  kernel /boot/zImage
  fdt /boot/tegra20-asus-sl101.dtb
  append root=/dev/mmcblk1p1 rootfstype=ext4 rootwait rw console=tty0 video=tegrafb loglevel=7
```

The persistent baseline hashes during keyboard development were:

```text
zImage
aaf847d5a15a5c673d921f87c3c08d45dd7ddff8185723dd7da804289265d630

tegra20-asus-sl101.dtb
7c938df062396a142f800c3807ba0d8f4255cd9ff8bfc8d09e83ee93b1dcb52a
```

Those hashes became our safety rail. Experimental work was not allowed to silently replace either file.

With that baseline the tablet already had native Debian, working SSH, storage, Wi-Fi, battery telemetry and Tegra DRM.

The conspicuous missing feature was the keyboard built into the slider.

## 3. Do not start with `tegra-kbc.c`

The first tempting lead was the Tegra keyboard controller driver, `drivers/input/keyboard/tegra-kbc.c`.

That would be a reasonable guess for a Tegra 2 tablet with a keyboard.

It was also wrong.

The SL101 is similar to the TF101 electrically, but the integrated slider keyboard is handled by an ASUS embedded controller rather than a Tegra matrix keyboard directly.

The useful historical source was ASUS's old Transformer EC driver. It showed the important topology:

```text
keyboard
   |
   v
ASUS / Nuvoton EC
   |
   +-- I2C EC address      0x19
   +-- DockRAM address     0x1b
   +-- AP_WAKE interrupt   Tegra GPIO S2
   +-- EC_REQUEST          Tegra GPIO S3
   |
   v
PS/2-style keyboard protocol
   |
   v
Linux serio -> atkbd -> input
```

The live EC identifies itself as:

```text
Model         : ASUS-EP102-DOCK
FW version    : SL101-0202
Config format : ECFG-0001
HW version    : PCBA-EP102
```

That was the decisive architectural clue.

## 4. Add the SL101 EC to the device tree

The modern Transformer EC series already defines the compatible string:

```text
asus,sl101-ec-dock
```

What the SL101 board description still needed was the actual device node.

On this machine the EC sits on the I2C mux leg represented by `&lvds_ddc`. The working node is:

```dts
&lvds_ddc {
    embedded-controller@19 {
        compatible = "asus,sl101-ec-dock";
        reg = <0x19>, <0x1b>;
        reg-names = "ec", "dockram";

        interrupt-parent = <&gpio>;
        interrupts = <TEGRA_GPIO(S, 2) IRQ_TYPE_LEVEL_LOW>;

        request-gpios = <&gpio TEGRA_GPIO(S, 3) GPIO_ACTIVE_LOW>;
    };
};
```

The kernel also needs:

```text
CONFIG_MFD_ASUS_TRANSFORMER_EC=y
CONFIG_SERIO_ASUS_TRANSFORMER_EC=y
CONFIG_SERIO=y
CONFIG_SERIO_LIBPS2=y
CONFIG_KEYBOARD_ATKBD=y
```

At this point we had enough for a first EC-enabled kernel.

## 5. Use kexec as the development loop

The biggest practical improvement in the whole bring-up was refusing to overwrite the known-good boot kernel for every experiment.

Instead, we used `kexec`.

The procedure was:

### Capture the known-good state

We installed a small diagnostics directory under:

```text
/root/sl101-diag/
```

Before a test:

```sh
/root/sl101-diag/snapshot.sh
```

That recorded the boot hashes, display state, battery state, I2C devices, serio/input devices and relevant kernel messages.

### Verify that power is safe

Do not start repeated kernel experiments on a marginal battery.

For example, just before the successful keyboard test the tablet reported:

```text
status=Charging
capacity=52
current_now=765000
current_avg=769000
ac_online=1
```

The earlier “charging bug” turned out to be an adapter problem, not a kernel problem.

### Copy the experimental kernel to RAM-backed temporary storage

We staged the test artifacts as:

```text
/tmp/sl101-kbd-zImage
/tmp/sl101-kbd.dtb
```

Then verified both the experimental files and the persistent boot files with SHA-256.

### Load, but do not execute, the test kernel

```sh
kexec -l /tmp/sl101-kbd-zImage \
    --dtb=/tmp/sl101-kbd.dtb \
    --command-line="$(cat /proc/cmdline)"
```

Verify:

```sh
cat /sys/kernel/kexec_loaded
```

A value of `1` means the new kernel is loaded.

At this stage nothing persistent has changed.

### Execute the RAM-only test boot

```sh
sync
kexec -e
```

If the experimental kernel is bad, a normal cold boot still goes through the untouched extlinux entry and known-good `/boot/zImage` and DTB.

That made debugging the EC much less stressful.

## 6. First success: the EC probes, but the keyboard still fails

The first EC kernel proved that the architecture and DT wiring were correct.

The controller appeared at I2C addresses `5-0019` and `5-001b`.

The MFD driver read the model and firmware correctly.

The serio child registered, and Linux created:

```text
N: Name="AT Raw Set 2 keyboard"
P: Phys=i2c-5-0019/serio0/input0
H: Handlers=sysrq kbd leds event3
```

This was a major milestone: the keyboard was no longer “missing”.

But `atkbd` still printed errors such as:

```text
atkbd serio0: keyboard reset failed on i2c-5-0019/serio0
atkbd serio0: Failed to deactivate keyboard
atkbd serio0: Failed to enable keyboard
```

That told us the failure had moved from discovery into protocol initialization.

The next question became very specific:

**Why was `atkbd` not receiving the expected PS/2 ACK and BAT bytes?**

## 7. Compare the modern driver with ASUS's old SL101 code

This is where the old vendor driver was useful again.

The current v10 ASUS Transformer EC series reads the EC event register at `0x6a` using a 32-byte transfer:

```c
i2c_smbus_read_i2c_block_data(client, ASUSEC_READ_BUF,
                              ASUSEC_ENTRY_SIZE, buf);
```

with:

```c
#define ASUSEC_ENTRY_SIZE 32
```

ASUS's SL101-era driver does something different:

```c
i2c_smbus_read_i2c_block_data(client, 0x6a, 8, ec_chip->i2c_data);
```

That eight-byte value was not cosmetic.

On the SL101, requesting/expecting the generic 32-byte event entry caused valid keyboard responses to disappear from the path to serio.

So the first functional correction was to make the event-read length variant-specific:

```c
static size_t asus_ec_read_size(const struct asus_ec_data *ddata)
{
    if (ddata->info->variant == ASUSEC_SL101_DOCK)
        return 8;

    return ASUSEC_ENTRY_SIZE;
}
```

and use that size for both EC buffer clearing and IRQ event reads.

I am intentionally limiting the upstream claim to SL101. The TF101 vendor family may share the behavior, but the hardware we physically proved is the SL101.

## 8. The second problem: PS/2 replies can be OBF-only

The modern serio driver routes packets to keyboard serio0 when the EC status contains `KBC` or `KEY`.

That works for ordinary key events.

It is not sufficient for keyboard commands.

During initialization, `atkbd` sends normal PS/2 commands such as reset, disable scanning and enable scanning. The EC can return command responses with the Output Buffer Full bit set but without KEY or KBC.

ASUS's original code treated a valid non-AUX OBF response as keyboard data.

So the routing rule needs to be:

```c
if (action & (ASUSEC_SMI_MASK | ASUSEC_SCI_MASK))
    return NOTIFY_DONE;
else if (action & ASUSEC_AUX_MASK)
    port_idx = 1;
else if (action & ASUSEC_OBF_MASK)
    port_idx = 0;
else
    return NOTIFY_DONE;
```

Because the AUX check happens first, touchpad responses still go to serio1. A remaining valid non-SMI/non-SCI OBF packet is delivered to the keyboard.

That is what allows PS/2 ACK bytes such as `0xfa` to reach `atkbd`.

## 9. The subtle v10 regression: packet length semantics

There was one more detail.

While instrumenting the EC we observed a keyboard reset response:

```text
03 09 fa aa
```

Interpreted as:

```text
03  = three bytes follow the count byte
09  = EC status
fa  = PS/2 ACK
aa  = keyboard BAT success
```

In other words, the first byte counts the bytes **after** itself: status plus payload.

The v9 version of the modern serio patch effectively forwarded `data[0] - 1` payload bytes after skipping the count and status bytes.

v10 changed that to `data[0] - 2` while tightening a bounds check to fix a possible out-of-buffer read.

The bounds fix was sensible; subtracting the additional byte was not.

For `03 09 fa aa`:

```text
v10: n = 3 - 2 = 1  -> forwards fa only
fixed: n = 3 - 1 = 2 -> forwards fa aa
```

Dropping `0xaa` explains why a keyboard reset can still fail even when the ACK reaches `atkbd`.

The safe fix is to retain the v10 upper bound while restoring the actual packet semantics:

```c
if (data[0] < 2 || data[0] > ASUSEC_ENTRY_SIZE)
    return NOTIFY_BAD;

n = data[0] - 1;
data += 2;
```

This is a particularly useful upstream finding because it is not simply an SL101 quirk. It corrects a regression introduced between v9 and v10 of the pending driver series.

## 10. Rebuild, kexec, type

With the three protocol changes in place:

1. SL101 event reads use eight bytes;
2. OBF-only non-AUX replies go to keyboard serio0;
3. the packet count forwards the complete payload;

we rebuilt the EC-enabled kernel and DTB.

The experimental kernel was copied to `/tmp`, hashes were checked, the persistent `/boot` artifacts were checked again, and the new kernel was loaded with `kexec -l`.

Then:

```sh
sync
kexec -e
```

The machine came back.

And the physical sliding keyboard worked.

That is the best kind of kernel debugging result: not merely a cleaner `dmesg`, but keys producing input on a 15-year-old tablet under a current mainline-derived kernel.

## 11. A small display detour that is worth documenting

During the test cycle it briefly looked as if the experimental kernel had broken the display stack.

It had not.

Tegra DRM was healthy:

```text
/proc/fb: 0 tegradrmfb
LVDS: connected
LVDS: enabled
mode: 1280x800
```

The screen was simply powered down in two independent places:

```text
/sys/class/graphics/fb0/blank = 4
/sys/class/backlight/backlight/bl_power = 4
```

The recovery was:

```sh
echo 0 > /sys/class/graphics/fb0/blank
echo 0 > /sys/class/backlight/backlight/bl_power
```

We then extended the existing `fix-backlight.service` so boot unblanks both the framebuffer and the PWM backlight.

That episode is a useful reminder not to call a driver “broken” until the kernel objects and power state have been checked separately.

## 12. What is actually worth upstreaming

The current ASUS Transformer EC series is already the right architecture. There is no reason to create a separate SL101 keyboard driver.

The useful contribution is small:

### MFD / EC core

Teach the core that the SL101 event window at `0x6a` is eight bytes and use that size in the clear-buffer and interrupt paths.

### serio / keyboard

Restore the correct packet-count semantics while keeping the v10 bounds check, and route valid OBF-only non-AUX responses to keyboard serio0.

### ARM Tegra device tree

Add the SL101 EC node under `&lvds_ddc` with EC/DockRAM addresses `0x19`/`0x1b`, GPIO S2 interrupt and GPIO S3 request.

The first two should be discussed directly with the active ASUS Transformer EC series because v10 is still a posted patch series rather than old, frozen code.

The device-tree addition belongs with the Tegra maintainers and can depend on the EC binding/driver series.

## 13. What I would do next

The debugging kernel should now become a boring kernel.

That means:

- remove temporary packet logging;
- give the build a distinct local version such as `6.18.45-sl101-ec1`;
- install it next to, not over, the known-good kernel;
- create two extlinux entries;
- cold-boot it repeatedly;
- test modifiers, autorepeat, special keys, slider mode, suspend/resume, touchscreen, Wi-Fi, audio, charging and display wake;
- then send the minimal fixes upstream.

Only after that would I consider changing distributions.

postmarketOS could absolutely consume this hardware work later, but switching from Debian to postmarketOS would not make the tablet “more native”. It is already running native Linux.

For now, the nicest result is simpler:

**an ASUS Eee Pad Slider SL101 boots current-ish mainline Linux into Debian Trixie, and its strange little built-in keyboard finally works.**

## References

- ASUS Transformer EC v10 patch series, July 21, 2026: https://patchew.org/linux/20260721095233.420823-1-clamor95%40gmail.com/
- Linux 6.18.45 SL101 device tree: https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/arch/arm/boot/dts/nvidia/tegra20-asus-sl101.dts?h=v6.18.45
- U-Boot ASUS Transformer/Slider T20 documentation: https://docs.u-boot.org/en/latest/board/asus/transformer_t20.html
- ASUS downstream TF101/SL101 kernel used for historical EC comparison: https://github.com/AndroidRoot/android_kernel_asus_tf101
