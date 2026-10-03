@projmgrauth
Set repo: /home/user/code/android-infra

Implement the assigned ASUS SL101 Tegra20 Grate Mesa25 lane autonomously, with focused reviewable code and meaningful validation. User explicitly requested two parallel ChatGPT operator prompts for texture and arithmetic support.

Read docs/sl101-nura-bringup.md and docs/sl101-grate-mesa25-runtime-fixes.patch first. Actual musl ARMv7 Nura hardware proof: private Mesa25 + Linux7.0.1-grate opened GR2D/GR3D, cleared RGB565 red via GR2D and rendered triangle via GR3D; readback 1352 green/2744 red, center green/corner red. Vertex immediate upload and fragment MOV immediates 0/1 have been fixed. Fragment compiler currently only MOV. Desktop works using pixman, GPU labwc not established. Never equate compilation with hardware success.

Immutable shared input is /home/user/code/android-infra/tmp/sl101-nura/dispatch-baseline-r3 (manifest adjacent). Copy it into your assigned lane directory and modify that copy ONLY. Do not edit the canonical tmp/sl101-nura/source/ported-source, preexisting devices-trunks source, shared pmbootstrap build/chroots, other lane files, or docs/sl101-nura-bringup.md. Do not commit/bulk-format unrelated dirty work. No SSH, live tablet actions, reboot, flash, package changes or replacing Mesa. Integration and hardware qualification belong to the coordinator after both lanes are reviewed. Existing other android-infra CI tasks do not authorize touching our port or committing dirty files.

Use installed project workflow if required: adopt/admit and bind the EXACT supplied OCP task ID, begin/checkpoint/submit typed result through ws-bridge agent_workflow and retain required independent review. Routine workflow setup is authorized. If no workflow contract applies, return an exact artifact/result reference. One project header is already supplied; do not add another. Do not claim filesystem access from composer text alone.

Deliver a patch against the immutable baseline, modified source copy, focused compiler/command tests exercising actual semantics and explicit rejection of unsupported inputs, short integration instructions and remaining limits. Use primary Grate/host1x source documentation when researching. Avoid stubs or silently claiming unsupported operations. Keep GPU state and compiler resource limits correct; validate before emitting commands.

Exact OCP task: SL101-GRATE-ARITHMETIC-20260930
Exclusive writable lane directory: /home/user/code/android-infra/tmp/sl101-nura/parallel/arithmetic

Implement fragment arithmetic needed by wlroots GLES2: ADD/MUL/MAD and common supported scalar/vector forms, correct swizzle/writemask/negate/saturate/temp handling, and arbitrary immediate values if supported by the hardware IR. Fix genuine ALU scheduling/dependency issues exposed by these operations. Own arithmetic lowering, immediate representation and ALU IR/packing. Do NOT implement TEX/sampler/resource emission; state the input/output contract for the texture lane. Both lanes may edit separate copies of fp/tgsi.c/IR; emit narrowly separated patches for deliberate coordinator merge. Test packed instructions and numeric semantics against simple reference arithmetic, including precision/resource limits and unsupported cases. Deliver implementation, not a design-only response.
