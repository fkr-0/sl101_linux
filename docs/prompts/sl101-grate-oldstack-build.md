# ANDROID-SL101-GRATE-OLDSTACK-01 — build self-consistent wlroots+labwc against grate Mesa 20.0

@projmgrauth
Set repo: android-infra.

Canonical lane: `ANDROID-SL101-GRATE-OLDSTACK-01`.

## Background

The ASUS SL101 (Tegra 2, armhf) needs GPU-accelerated Wayland. The only working GPU driver is **grate** (github.com/grate-driver), which is a Mesa 20.0 fork. The system runs Debian trixie with Mesa 25 + wlroots 0.18 + labwc — these are ABI-incompatible with grate Mesa 20.0.

**Goal**: build a self-consistent old stack (wlroots + labwc + grate Mesa 20.0 + matching libdrm) that runs as a standalone bundle on the SL101 without touching system Mesa.

## Approach

Install the entire stack into `/opt/grate/` so it doesn't conflict with system packages. Launch labwc with `LD_LIBRARY_PATH=/opt/grate/lib/arm-linux-gnueabihf` to use the grate stack.

## Version compatibility matrix

Find compatible versions:
- **grate Mesa**: branch `grate` of `https://github.com/grate-driver/mesa.git` — Mesa 20.0-devel, provides libEGL, libGLESv2, libgbm, libglapi, grate_dri.so
- **grate libdrm**: master of `https://github.com/grate-driver/libdrm.git` — provides libdrm + libdrm_tegra
- **wlroots**: needs a version that works with Mesa 20.0's GBM (no `gbm_bo_get_fd_for_plane`). wlroots 0.15.x or 0.16.x should work. Check the wlroots changelog for when `gbm_bo_get_fd_for_plane` became required — that's the upper bound.
- **labwc**: needs a version compatible with the chosen wlroots. labwc 0.6.x matched wlroots 0.16.
- **wayland/wayland-protocols**: use system versions if ABI-compatible, otherwise bundle them too.

## Steps

1. **Research version bounds**: check wlroots git history for when `gbm_bo_get_fd_for_plane` was introduced as a hard requirement. Pick the latest wlroots that doesn't need it.

2. **Cross-compile in Docker** (debian:bookworm-slim, armhf cross toolchain — same pattern as existing grate build):
   - Build grate libdrm → `/opt/grate/`
   - Build grate Mesa → `/opt/grate/` (gallium-drivers=grate,swrast, platforms=wayland, gbm=true, egl=true, gles2=true)
   - Build compatible wlroots → `/opt/grate/` (link against the grate Mesa just built)
   - Build compatible labwc → `/opt/grate/` (link against that wlroots)

3. **Package as tarball**: `grate-oldstack-armhf.tar.gz` that extracts to `/opt/grate/`

4. **Launcher script**: `run-labwc-grate.sh` that sets:
   ```sh
   export LD_LIBRARY_PATH=/opt/grate/lib/arm-linux-gnueabihf
   export MESA_LOADER_DRIVER_OVERRIDE=grate
   export LIBSEAT_BACKEND=builtin
   export XDG_RUNTIME_DIR=/run/user/0
   export LIBGL_DRIVERS_PATH=/opt/grate/lib/arm-linux-gnueabihf/dri
   exec /opt/grate/bin/labwc
   ```

## Constraints

- Target: armhf (armv7l, hard-float), Debian trixie
- Tegra 2 is GLES2-only, no compute/tessellation
- Python 3.11 needed for Mesa 20.0 (getchildren() removed in 3.9+, use bookworm base)
- The `-fcommon` flag is needed for GCC 12+ (Mesa 20.0 has duplicate tentative definitions)
- Cross-file must NOT include x86_64 pkg-config paths (causes linker to pick up wrong libs)
- wlroots needs `libseat-dev:armhf`, `libinput-dev:armhf`, `libpixman-1-dev:armhf`, `libxkbcommon-dev:armhf`

## Output

Dockerfile, build.sh, deploy script, launcher script. The result should be a single tarball that you scp to the SL101 and extract to get GPU-accelerated labwc.
