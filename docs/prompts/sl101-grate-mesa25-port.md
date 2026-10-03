# ANDROID-SL101-GRATE-MESA25-PORT — port grate Tegra 2 gallium driver to Mesa 25

@projmgrauth
Set repo: android-infra.

Canonical lane: `ANDROID-SL101-GRATE-MESA25-PORT`.

## Background

The ASUS Eee Pad Slider SL101 has a Tegra 2 SoC with a gr3d GPU. The only open-source 3D driver is the **grate** project (github.com/grate-driver). Their Mesa fork lives on the `grate` branch of `https://github.com/grate-driver/mesa.git` and is based on **Mesa 20.0.0-devel** (circa 2019).

The SL101 runs Debian trixie with **Mesa 25.0.7** system libraries. wlroots 0.18 / labwc depend on GBM/EGL symbols that only exist in Mesa 21+. We **cannot** mix a Mesa 20.0 DRI driver with Mesa 25 libEGL — the internal DRI ABI is incompatible.

**Goal**: port the grate gallium driver (`src/gallium/drivers/grate/`) and its winsys (`src/gallium/winsys/grate/`) from the grate Mesa 20.0 fork to Mesa 25.0.7 (or current Mesa main), producing a `grate_dri.so` that loads under the system Mesa 25 stack.

The grate driver also requires `libdrm_tegra` from `https://github.com/grate-driver/libdrm.git` (master branch). This libdrm is ABI-compatible with system libdrm and can overlay it without issue.

## What lives where

- **grate Mesa fork**: `https://github.com/grate-driver/mesa.git`, branch `grate`
  - `src/gallium/drivers/grate/` — the gallium driver (gr3d GPU command submission, shader compiler, state tracker)
  - `src/gallium/winsys/grate/drm/` — the DRM winsys (talks to kernel tegra DRM via libdrm_tegra)
  - `src/gallium/auxiliary/target-helpers/drm_helper.h` — has `pipe_grate_create_screen()` wiring
  - `src/gallium/targets/dri/target.c` — DRI target registration
  - Various `meson.build` files register the `grate` driver option

- **grate libdrm**: `https://github.com/grate-driver/libdrm.git`, master
  - Extends upstream libdrm with tegra-specific ioctls for channel/job submission

- **Mesa 25 (target)**: `https://gitlab.freedesktop.org/mesa/mesa.git`, branch `main` or tag `mesa-25.0.7`

## Task breakdown — 4 sequential prompts

### Prompt 1 of 4 should be run first, the rest can run in parallel after it.

---

## Prompt 1: API delta analysis

**Objective**: Produce a detailed diff of the gallium driver API between Mesa 20.0 and Mesa 25.0, focused on what the grate driver uses.

**Steps**:
1. Clone both Mesa repos (grate branch and mesa-25.0.7 tag)
2. Identify every gallium API header the grate driver includes or references:
   - `src/gallium/include/pipe/p_screen.h`
   - `src/gallium/include/pipe/p_context.h`
   - `src/gallium/include/pipe/p_state.h`
   - `src/gallium/include/pipe/p_defines.h`
   - `src/gallium/auxiliary/util/u_*`
   - Any others found via `grep -rh '#include' src/gallium/drivers/grate/`
3. For each header, diff the Mesa 20.0 version against Mesa 25.0.7
4. Catalog every breaking change:
   - Renamed/removed structs, fields, or enums
   - Changed function signatures in `pipe_screen` and `pipe_context` vtables
   - New required vtable entries (functions that must be non-NULL)
   - Removed helper functions from `u_*` utilities
   - Changed `pipe_resource` / `pipe_surface` / `pipe_transfer` layouts
5. For the DRI loader interface (`src/gallium/frontends/dri/` in Mesa 25, was `src/gallium/state_trackers/dri/` in Mesa 20), document:
   - How a gallium driver registers itself (the `driDriverAPI` / `pipe_loader` mechanism)
   - What changed in screen creation / `drm_driver_descriptor`

**Output**: A markdown document `grate-mesa25-api-delta.md` listing every breaking change with old vs new signatures, categorized by severity (trivial rename, signature change, semantic change, removed entirely). This is the map for prompts 2-4.

---

## Prompt 2: Driver source port

**Objective**: Port `src/gallium/drivers/grate/` to compile against Mesa 25 gallium headers.

**Prerequisites**: The API delta document from Prompt 1.

**Steps**:
1. Copy the grate driver directory into a Mesa 25 source tree at `src/gallium/drivers/grate/`
2. Copy the winsys at `src/gallium/winsys/grate/drm/`
3. Work through every compilation error using the API delta as a guide:
   - Update struct field names and types
   - Implement any new required `pipe_screen` / `pipe_context` vtable entries (stub with no-op or minimal implementation if the feature isn't relevant to Tegra 2, e.g. compute shaders, tessellation)
   - Replace removed utility functions with their Mesa 25 equivalents
   - Update `pipe_resource` / `pipe_transfer` usage
4. Do NOT attempt to "modernize" the driver beyond what's needed to compile — preserve the original logic
5. Key areas likely to need work:
   - `pipe_screen::resource_create` / `resource_from_handle` — handle format may have changed
   - `pipe_context::transfer_map` / `transfer_unmap` — the transfer API changed significantly around Mesa 21-22
   - `pipe_context::create_surface` — surface struct changes
   - TGSI vs NIR — Mesa 25 may require NIR. The grate driver uses TGSI. Check if `PIPE_SHADER_IR_TGSI` is still accepted or if a TGSI-to-NIR pass is required
   - `u_upload_mgr` / `u_suballoc` API changes

**Output**: A patch series or branch with the ported driver that compiles (warnings OK, but no errors) against Mesa 25.0.7 headers. Include a list of all stub functions added.

---

## Prompt 3: Build system integration

**Objective**: Wire the grate driver into Mesa 25's meson build system.

**Steps**:
1. Study how an existing simple gallium driver (e.g. `lima`, `panfrost`, or `etnaviv`) is registered in Mesa 25:
   - `src/gallium/drivers/*/meson.build`
   - `src/gallium/targets/dri/meson.build`
   - `src/gallium/meson.build` — the `gallium_drivers` option
   - `meson_options.txt` or `meson.options` — where driver names are listed
2. Add `grate` to the gallium drivers list in the build system
3. Create/update `src/gallium/drivers/grate/meson.build` for Mesa 25's build conventions
4. Create/update `src/gallium/winsys/grate/drm/meson.build`
5. Wire the DRI target so `grate_dri.so` gets built
6. Add `libdrm_tegra` as a dependency (it comes from the grate-driver/libdrm fork, already installed at `/build/install/`)
7. Test that `meson setup` accepts `-Dgallium-drivers=grate,swrast` without error

**Output**: The meson.build changes needed, as a patch. Include the exact meson configure command.

---

## Prompt 4: Cross-compile and smoke test recipe

**Objective**: Produce a working Dockerfile + build script that cross-compiles the ported grate Mesa 25 for armhf and packages it.

**Prerequisites**: Ported driver source from Prompt 2, build system from Prompt 3.

**Context**: We already have a working cross-compile setup for grate Mesa 20.0:
- Docker base: `debian:bookworm-slim` (Python 3.11, needed because Mesa 20 broke on 3.13)
- For Mesa 25, `debian:trixie-slim` should work (Mesa 25 supports Python 3.13)
- Cross toolchain: `crossbuild-essential-armhf`
- The armhf-pkg-config wrapper pattern works; replicate it
- Build grate libdrm first, then Mesa, package as tarball

**Steps**:
1. Write `Dockerfile` with cross-compile toolchain for armhf
2. Write `build.sh` that:
   - Clones and builds grate libdrm (master branch)
   - Clones Mesa 25.0.7 (or applies the grate patches to it)
   - Configures with `-Dgallium-drivers=grate,swrast -Dplatforms=wayland -Dgbm=enabled -Degl=enabled -Dgles2=enabled -Dglx=disabled -Dllvm=disabled`
   - Cross-compiles for armhf
   - Packages output as `grate-mesa25-armhf.tar.gz`
3. The output tarball should overlay cleanly onto a Debian trixie armhf system at `/usr/lib/arm-linux-gnueabihf/`
4. Include a smoke-test script for the SL101 that:
   - Extracts the tarball
   - Runs `ldconfig`
   - Tests: `MESA_LOADER_DRIVER_OVERRIDE=grate eglinfo` or `MESA_LOADER_DRIVER_OVERRIDE=grate glxinfo -B`
   - Launches labwc without `WLR_RENDERER=pixman` to test real GPU rendering

**Output**: Dockerfile, build.sh, deploy-and-test.sh — ready to run.

---

## Important constraints

- The Tegra 2 gr3d GPU is **very** simple: OpenGL ES 2.0 only, no compute, no tessellation, no geometry shaders. Many Mesa 25 features can be stubbed out.
- The grate driver uses **TGSI** IR, not NIR. If Mesa 25 requires NIR, the TGSI-to-NIR translation pass (`nir/tgsi_to_nir`) should handle it, but this needs verification.
- The kernel DRM driver is `tegra` (mainline, `CONFIG_DRM_TEGRA=y`). It exposes `/dev/dri/card0`. The grate userspace driver talks to it via `libdrm_tegra` ioctls.
- Do not attempt to use the mainline Mesa `tegra` gallium driver — it's a pass-through/wrapper that doesn't do 3D, only display. The `grate` driver is the one that does actual GPU command submission.
- Target: armhf (armv7l, hard-float). Not aarch64.
