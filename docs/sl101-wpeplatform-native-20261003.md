# SL101 WPEPlatform-native browser harness — 2026-10-03

Canonical task: `SL101-LINUX-WPEPLATFORM-NATIVE-HARNESS-20261003`
Catalog prompt: `sl101-linux-wpeplatform-native-harness-20261003-v1`
Scope: offline host work only. No SL101 deployment, boot, desktop, browser-profile,
kernel, graphics-device, mount or package mutation was performed by this lane.

## Result

A forward WPEPlatform-native qualification path now exists independently of the
legacy Cog/libwpe shell. The reference launcher is the **WPE WebKit 2.54.0-2
MiniBrowser shipped inside the exact Debian armhf runtime already archived in
this repository**. That is preferable to guessing a new C launcher against
headers that are not available in the offline evidence set.

The path is deliberately software-first. Mesa softpipe/swrast is the default;
the reviewed private Grate overlay is an explicit opt-in. WebKit
Bubblewrap/xdg-dbus-proxy sandboxing remains mandatory. WPE 2.54's Skia default
is preserved unless a separate comparison explicitly requests the compatibility
setting. GBM/DMA-BUF, WebGL and media acceleration remain separate later gates.

Run the host-only evidence check:

    python3 scripts/sl101-wpeplatform-host-qualify.py

The launcher is intended to be copied into and executed **inside** a future
prepared Debian armhf browser root by a separate serialized device lane:

    SL101_WPE_RENDERER=software sh scripts/sl101-wpeplatform-launch.sh https://example.org/

It contains no SSH, mount, chroot, package installation, compositor control or
boot action.

## Exact offline engine/package evidence

The immutable package set under
`work/sl101-wpe-armhf-build-qualification-20261003/wpe-audit/packages/`
contains:

| package | version | architecture | role |
| --- | --- | --- | --- |
| `libwpewebkit-2.0-1` | `2.54.0-2` | armhf | current WPE engine + WPEPlatform + MiniBrowser |
| `libwpe-1.0-1` | `1.16.3-2` | armhf | legacy compatibility ABI, not the new launcher API |
| `libwpebackend-fdo-1.0-1` | `1.16.1-1+b1` | armhf | legacy Cog compatibility backend |
| `cog` | `0.18.5-1` | armhf | compatibility harness only |
| GStreamer base/good runtime | `1.28.7-1` family | armhf | media runtime |

The exact WPE runtime package SHA-256 is:

    0b3713cae5520fb44a6fcb099b0b23b8f2802bf3e3a57415fc36b9616bc84ffb
    libwpewebkit-2.0-1_2.54.0-2_armhf.deb

Its archived Debian control data requires, among other normal WebKit
dependencies, `bubblewrap`, `xdg-dbus-proxy`, `libseccomp2`, `libdrm2`,
`libgbm1`, and the Wayland client/EGL/server libraries. Sandbox failure is a
qualification failure, not a reason to launch with a bypass.

The package contains and the debug-symbol-merged audit verifies:

    /usr/lib/arm-linux-gnueabihf/libWPEWebKit-2.0.so.1.11.3
    /usr/lib/arm-linux-gnueabihf/wpe-webkit-2.0/MiniBrowser
    /usr/lib/arm-linux-gnueabihf/wpe-webkit-2.0/WPEGPUProcess
    /usr/lib/arm-linux-gnueabihf/wpe-webkit-2.0/WPENetworkProcess
    /usr/lib/arm-linux-gnueabihf/wpe-webkit-2.0/WPEWebProcess

### WPEPlatform API surface verified from the exact binary

Host `readelf -Ws` against the archived `libWPEWebKit-2.0.so.1.11.3`
confirms WPEPlatform symbols including:

- display/toplevel: `wpe_display_create_toplevel`,
  `wpe_display_get_settings`, `wpe_toplevel_set_title`,
  `wpe_toplevel_resize`, fullscreen/maximize/minimize operations;
- Wayland: `wpe_display_wayland_new`, `wpe_display_wayland_connect`,
  `wpe_display_wayland_get_wl_display`,
  `wpe_display_wayland_get_wl_shm`,
  `wpe_view_wayland_get_wl_surface`;
- alternate display backends: `wpe_display_headless_new` and
  `wpe_screen_drm_get_type`;
- WebKit integration: `webkit_web_view_new`,
  `webkit_web_view_load_uri`, `webkit_web_view_get_wpe_view`,
  `wpe_view_get_display`, and `wpe_view_get_toplevel`.

This proves exact binary/API names and the presence of the WPEPlatform-native
MiniBrowser. It does **not** manufacture C declarations or ABI signatures.

### Offline development-header gap

There is a deliberate **development-header gap** in this lane: neither a
matching WPE 2.54 development package, its public headers nor its pkg-config
files are present in the migrated offline evidence, and the host apt cache does
not contain them. Therefore this task does not claim an unverified Debian
development package name, header path, pkg-config module, or hand-written
function signature.

A custom C shell should only be added after the exact 2.54.0-2 development
package/source bundle is archived and hash-pinned. Until then, the upstream-built
MiniBrowser from the exact engine package is the smaller and more trustworthy
native WPEPlatform harness.

## 2026-10-04 runtime-closure correction

The CPU audit described below was a **selected-package** audit, not a complete
installed-runtime audit. The fetch script downloaded nine named WPE/Cog/GStreamer
packages but did not resolve and extract their full Debian dependency closure.

That distinction is material. Subsequent live debugging captured a page-load
SIGILL in the `ImageDecoder` thread inside stock `libwebp.so.7`, at
`vldr d16` followed by NEON `vst1.32`. WPE WebKit 2.54.0-2 declares
`libwebp7` as a dependency, but libwebp was not present in the 136-object audit.

Therefore the 136-object result remains valid only for the objects it actually
contains. It must not be used as proof that the complete browser root is
Tegra20-safe. `scripts/sl101-wpeplatform-host-qualify.py` now fails closed
until a complete prepared root passes
`scripts/sl101-wpe-runtime-closure-audit.py` and the resulting receipt is
revalidated against that same root with
`scripts/sl101-wpeplatform-host-qualify.py --closure-root /path/to/root`.

See `docs/sl101-wpe-runtime-closure-audit-20261004.md` for the corrected
full-runtime contract.

## CPU / ARMHF qualification

The raw stripped-object scan `wpe-audit/wpe-elf-audit.txt` produced many false
positives because disassembly crossed stripped symbol/data boundaries. It must
not be used as the final CPU verdict.

The later debug-symbol-merged audit is authoritative for this selected package set only:

    work/sl101-wpe-armhf-build-qualification-20261003/
      wpe-debug-audit/merged-elf-audit.json

Result:

    ELF count: 136
    failures: 1

The only remaining failure is:

    usr/lib/arm-linux-gnueabihf/gstreamer1.0/gstreamer-1.0/gst-ptp-helper

That helper uses an out-of-baseline VFP register and is already excluded by the
private-root preparation. It is not needed for normal page rendering or browser
audio. The WPE engine, MiniBrowser, WPEWebProcess, WPENetworkProcess and
WPEGPUProcess all pass the merged policy with ARMv7, VFPv3-D16, hard-float
attributes and no detected NEON/Q-register/high-D-register use.

The private Grate overlay remains separately green:

    SHA-256 12388168bd458268ea31b9742acac7e27d293dffebaf0dee141cce1a3304a215
    Mesa 25.0.7
    18 ELF objects, 0 audit failures
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard
    LLVM disabled; Gallium grate,softpipe

This selected-package static result cannot prove the complete transitive runtime or JSC-generated code on Tegra20 is safe. A full-root closure audit plus the live CPU/JIT execution gate are both required.

## Reproducible armhf packaging plan

Reuse the hash-pinned Debian armhf base/snapshot contract rather than building
another root in parallel:

    base rootfs sha256:
      9312e8243384574a9ab866dedfdd93bccf5359b4163b9bf22db6a770bc0afdc9
    Debian snapshot:
      20261003T000000Z
    engine:
      libwpewebkit-2.0-1=2.54.0-2
    architecture:
      armhf

A private-root preparation lane may install the exact engine plus its resolved
snapshot dependencies, CA certificates and fonts. It must retain `bubblewrap`
and `xdg-dbus-proxy`, remove the incompatible `gst-ptp-helper`, archive the
final dpkg manifest/hashes, and run
`scripts/sl101-wpeplatform-host-qualify.py` against the immutable host evidence
before transfer.

For a source rebuild the target contract remains:

    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard

but requested flags are not acceptance evidence. The resulting engine, JSC,
Skia, GStreamer and launcher objects must pass the same debug-symbol-backed ELF
audit. A source rebuild is not started here because no complete hash-pinned WPE
2.54 source/build-dependency bundle is present offline.

## Launcher isolation contract

`scripts/sl101-wpeplatform-launch.sh` is not a deployer. A serial device lane
places it inside an already prepared private Debian root and provides the
Wayland/audio/device bindings through that lane's reviewed namespace setup.

Software mode is the default:

    LIBGL_ALWAYS_SOFTWARE=1
    GALLIUM_DRIVER=softpipe
    MESA_LOADER_DRIVER_OVERRIDE=swrast

Grate is explicit via `SL101_WPE_RENDERER=grate` and selects only the private
overlay under `/opt/grate-glibc/usr/lib/arm-linux-gnueabihf` using
`LIBGL_DRIVERS_PATH`, `GBM_BACKENDS_PATH`, and
`MESA_LOADER_DRIVER_OVERRIDE=grate`.

The launcher requires `bwrap` and `xdg-dbus-proxy`, rejects the known WebKit
sandbox-disable environment, and never passes a sandbox bypass flag.

## Separate qualification gates

Success at one gate does not imply the next.

1. **CPU / loader / JSC** — exact loader/runtime hashes, static ELF audit,
   MiniBrowser HTTPS+JS startup, then JIT-heavy JS without SIGILL.
2. **Software renderer baseline** — MiniBrowser on Wayland with softpipe/swrast,
   correct pixels/input/scroll/audio, normal Bubblewrap subprocesses, zero new
   kernel graphics faults.
3. **Private Grate EGL** — identify Grate/Tegra and expected GLES2/EGL
   capabilities; no system Mesa replacement.
4. **GBM / DMA-BUF** — allocation/import/export/synchronization tested directly;
   process maps prove private overlay; zero fault/reset delta.
5. **Skia** — WPE 2.54 default is a **separate gate** from EGL creation.
6. **WebGL** — WebGL1/ANGLE is a **separate gate** after ordinary browser GPU
   composition is correct; WebGL2 is not inferred from GLES2.
7. **Media** — software decode first; V4L2/hardware decode and sandbox device
   access are separate.
8. **Soak / promotion** — memory, CPU, GPU activity, thermals, page correctness,
   audio/video and recovery before launcher/default-browser integration.

## Serial device-qualification handoff

This task stops before the device boundary. The next device owner should:

1. acquire the existing SL101 qualification lock and verify CID/kernel;
2. reuse the prepared private Debian root; do not replace Nura/musl libraries;
3. verify `gst-ptp-helper` is absent and package/hash receipts match this host
   evidence;
4. copy only the WPEPlatform launcher into the private root;
5. start with `SL101_WPE_RENDERER=software`;
6. capture MiniBrowser/WPE subprocess `NoNewPrivs`/`Seccomp` state and
   Bubblewrap presence, HTTPS+JS, toplevel pixels/input/scroll and dmesg delta;
7. only after software acceptance, run one Grate pass and prove mapped-library
   provenance;
8. qualify GBM/DMA-BUF, Skia, WebGL and media one at a time;
9. tear down without changing default pixman labwc, Firefox recovery, host Mesa,
   boot state or the Cog deployment.

There is intentionally no automatic deployment command in this lane.

## Host verification

Focused tests:

    python3 -m unittest tests.test_sl101_wpeplatform_native

Repository checks:

    make test
    make check

The host qualifier emits typed JSON evidence and performs no network or device
access.
