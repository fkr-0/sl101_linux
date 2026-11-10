# Cog/WPE Wayland JS injection for Sway (candidate; 2026-11-10)

This integration follows the **already-tested** Cog 0.18.5 / WPE WebKit
2.54.0 armhf WebProcess extension in
`tools/sl101-cog-web-extension/` and
`docs/sl101-cog-kms-injection-20261104.md`.
It is a **host-only code change**, not evidence of live Sway injection or GPU
pixel correctness. The production default must not change until installation,
hardware and rollback checks pass.

## Launch contract

- Installed host launcher:
  `/usr/local/bin/sl101-cog-wpe-root`
  (source: `docs/sl101-device-config/usr/local/bin/sl101-cog-wpe-root`).
- Enter helper:
  `/usr/local/libexec/sl101-cog-wpe-enter`.
- Browser source JS:
  `/opt/sl101-cog-wpe-debian/var/lib/sl101-cog-chrome.js`.
- ARMv7 extension module:
  `/opt/sl101-cog-wpe-debian/usr/lib/sl101-cog-extensions/libsl101-cog-inject.so`.
- Browser-world snapshot:
  `/usr/lib/sl101-cog-extensions/sl101-cog-script.js` inside the browser
  mount namespace and WebProcess sandbox.

The launcher defaults to injecting the browser chrome. It checks that the
source and module exist and are regular non-symlink files, reads the source
as browser uid 1000, writes a separate temporary snapshot with restrictive
permissions and atomically renames it. Failure is **fatal** rather than
silently disabling the extension. An explicit `--no-inject` keeps the
previous no-extension launch path without copying a script.

`--inject-script /var/lib/custom.js` replaces the chroot source; it does
not broaden filesystem visibility or disable the WebProcess sandbox.
The private enter helper receives an explicit snapshot-ready state.
Both software and GPU Cog Wayland launchers pass
`--web-extensions-dir=/usr/lib/sl101-cog-extensions`, and
`SL101_COG_INJECT_SCRIPT` identifies the **sandbox-visible snapshot**.
Older callers without this state retain no-injection behavior.

Host syntax and 10 isolated source-snapshot tests:

    sh -n docs/sl101-device-config/usr/local/bin/sl101-cog-wpe-root
    sh -n docs/sl101-device-config/usr/local/libexec/sl101-cog-wpe-enter
    python3 -m unittest discover -s tests -p test_sl101_cog_wayland_injection_20261110.py -v

## Deployment gate

The SL101 device is not currently accessible through the configured
SSH key. **No install or runtime test was carried out in this lane.**
After authenticated access and operator lock ownership:

1. Verify exact `.106` hostname, SD CID, kernel, installed Cog/WPE
   ABI and matching WebProcess extension SHA256. Read-only first.
2. Confirm the Nura desktop and browser are quiescent; save originals of
   both scripts and the JS source/module/snapshot.
3. Deploy these two small scripts with their original mode 0755. Build
   or install the pinned ARMv7 extension only if absent or attested
   against the known source. Do not alter system Mesa or WebKit binaries.
4. Launch software Cog with `--no-inject` as the control. Then launch
   with injection, checking console warnings, browser WebProcess load,
   14-frame main/cross-origin/dynamic-nav fixture and Ctrl+L omnibar.
5. In a **separate** bounded session try GPU Cog/Grate. Compare actual
   page screenshots and framebuffer pixels with the software control;
   inspect kernel fault deltas and process maps. Existing evidence of
   successful `window-object-cleared` JS is not GPU conformance.
6. Roll back the two launcher scripts and any changed extension source/
   snapshot if either route fails; do not restart Sway unnecessarily.

The separate direct-KMS Cog launcher already implements injection in an
isolated namespace; this change does not modify the KMS backend or its
watchdog. Neither route is yet accepted as a default graphics service.
