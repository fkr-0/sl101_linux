# SL101 FBL03 — fragment DP2 and Skia GPU raster, 2026-11-03

OCP: SL101-LINUX-03-PROMPT-FP-DP2-AND-SKIA-GPU-20261103-9AE938

## Verified host-side findings

- Current shared `build/mesa-grate-clean/mesa-25.0.7/src/gallium/drivers/grate/fp/tgsi.c` lacks DP2, DP3 and DP4 dispatch. Patch 0012 is **not integrated** into that current build copy.
- Tracked `patches/mesa-25.0.7/0012-grate-fp-frc-dp3-dp4.patch` contains a dimension-parametric `fp_emit_dot`: first-component MUL, subsequent MAD, scratch-register ownership and destination alias protection.
- Candidate `0037-grate-fp-dp2.patch` adds the two-component lowering by reusing `fp_emit_dot(..., 2)`. **Apply 0012 before 0037** in a lane-specific build copy. Lane 06 owns series/build/deploy tooling.
- Supplied prior report records Skia GPU raster TGSI opcode 71 (DP2); this is **not newly measured evidence**.

## Skia shader/resource matrix

| Blocker | Evidence | Remaining qualification |
| --- | --- | --- |
| Fragment DP2 | Prior report: opcode 71; host patch 0037 prepared | Apply after 0012, build, compile Skia shaders and inspect pixels |
| Fragment DP3/DP4 | Patch 0012 contains lowering but shared build copy lacks it | Integrate and verify both opcodes independently |
| Fragment uniforms | Current host audit: 32 scalar slots, or 8 vec4; below GLES2 minimum of 16 vec4 | Capture uniform usage for every real Ganesh shader |
| Varyings | No complete Ganesh dump available to lane 03 | Enumerate actual varying consumption and compiler failures |
| Control flow | Existing static audit expects IF/ELSE/LOOP/KILL absent | Enumerate shader opcodes and real failures |
| Stencil | S8 EGL config does not imply stencil tests work | Pixel test stencil-dependent clipping |
| Frame output | Prior WebProcess GR3D submits exist, but scanout failed | Independently measure frames and correct on-screen pixels |
| GPU raster | No new multi-page capture performed | Compare CPU and opt-in GPU Skia raster per page |

## Recommendation and coordination

Keep `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` as the Tegra20 production default. GPU composition is not proof of GPU rasterization; rAF, EGL initialization and ioctl counts alone are not pixel proof. Do not spoof caps. Live `GRATE_DEBUG=tgsi` shader captures and any device modification **require durable handoff from lane 01**. No hardware mutation was performed in this lane.
