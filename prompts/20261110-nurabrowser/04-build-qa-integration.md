# Canonical implementation handoff

@projmgrauth
Set repo: sl101_linux

**Implement real code, not just a plan.** Task is host-only; device
`192.168.23.106` is offline after an unconfirmed RC2 kexec boot. Do NOT
SSH, reboot, flash, KMS test, deploy or touch either real tablet. Preserve all
existing uncommitted work (Mesa, Ansible and sessions) and work ONLY on owned
files. Begin authenticated workspace session in checkout mode, coordinate
claims, checkpoint progress and verify tests. Read `AGENTS.md`,
`nura-browser/README.md` and the immutable cross-lane ABI
`nura-browser/include/nurabrowser/contract.h` first.

Use **WPE WebKit 2.54+ WPEPlatform**, headers `<wpe/webkit.h>`,
`<wpe/wpe-platform.h>`, pkg-config `wpe-webkit-2.0`,
`wpe-platform-2.0`. Not `libwpe` legacy/WPEBackend-fdo and not a
Cog fork. WPE_PLATFORM=headless/wayland/drm; hardware access is out of
scope. Real WebKit API names must be confirmed against installed headers
or upstream WPE 2.54 docs; if headers unavailable, leave explicit
host-crossbuild gate, NEVER fake a passing ARMHF compilation.

Canonical eventual user command: `,browse` ONLY (hard cutover);
no alias manifest and no permanent old `sl101-browse` public executable.
Target Tegra2 ARMHF VFPv3-D16 **without NEON**; private GLIBC WebKit
browser root; WebKit sandbox must not be disabled. No dynamic shell
execution from pages, browser URL input or IPC.

Deliver source files, tests and precise evidence. Leave a concise
implementation handoff with tests, limitations and owned paths. Do not
change `contract.h`, other workers' directories, shared `Makefile`,
`AGENTS.md`, or Ansible while workers run; coordinator integrates.

# Worker D — cross-build, test and packaging integration

Canonical OCP Task: `SL101-NURABROWSER-04-BUILD-QA-20261110`
Priority 85. Own ONLY `nura-browser/meson.build`,
`nura-browser/meson_options.txt`, `nura-browser/packaging/**`,
`nura-browser/scripts/**`, `nura-browser/tests/**`,
`nura-browser/docs/build-qualification.md`.
Read immutable contract and coordinate API with A/B/C; **do not edit
their source files or their claim**.

Provide actual Meson C11 build linking GLib/GIO/GObject,
`wpe-webkit-2.0`, `wpe-platform-2.0` and JSON-GLib if used by control.
Compile sources expected under `src/engine/*.c`,
`src/navigation/*.c`, `src/control/*.c` (glob not allowed in Meson;
coordinate actual filenames). No use of `libwpe` backend-fdo.
Build ARMHF glibc using pinned Debian WebKit 2.54.0-2 dev headers and
library closure; verify native toolchain headers if installed; otherwise
implement a fail-closed build-qualification check that states missing
headers exactly and never claims runtime success. Inspect historical
`scripts/sl101-wpeplatform-host-qualify.py`, archived Debian armhf
package evidence and `work/sl101-wpeplatform-native-20261003`.
Avoid NEON and forbidden optimizations (arch=armv7, ABI=gnueabihf,
VFPv3-D16), never globally replace Mesa or WebKit libs.
Implement `nura-browser/scripts/launch.sh` or `,browse` **source**
which uses an existing prepared private Debian browser root only after
identity and ABI verification; software-first default, explicit Grate GPU
mode with pinned overlay, WPE_PLATFORM headless/Wayland/DRM checks, and
sandbox preserved; no SSH/reboot/deploy to tablet.
Provide offline tests for CLI options, shell safety, Meson deps,
no legacy APIs, ABI/NEON auditing and renderer mode gate.
Add local packaging manifest derived from build output (hashes for
artifact integrity okay; never a duplicate command/alias map).
A full build/test log with exit code is mandatory; if packages unavailable,
report blocker and what can be proved on host. Record separate readiness
of source/compiled host/ARMHF/on-device.
