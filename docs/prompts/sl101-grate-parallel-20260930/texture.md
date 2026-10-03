@projmgrauth
Set repo: /home/user/code/android-infra

Implement the assigned ASUS SL101 Tegra20 Grate Mesa25 lane autonomously, with focused reviewable code and meaningful validation. User explicitly requested two parallel ChatGPT operator prompts for texture and arithmetic support.

Read docs/sl101-nura-bringup.md and docs/sl101-grate-mesa25-runtime-fixes.patch first. Actual musl ARMv7 Nura hardware proof: private Mesa25 + Linux7.0.1-grate opened GR2D/GR3D, cleared RGB565 red via GR2D and rendered triangle via GR3D; readback 1352 green/2744 red, center green/corner red. Vertex immediate upload and fragment MOV immediates 0/1 have been fixed. Fragment compiler currently only MOV. Desktop works using pixman, GPU labwc not established. Never equate compilation with hardware success.

Immutable shared input is /home/user/code/android-infra/tmp/sl101-nura/dispatch-baseline-r3 (manifest adjacent). Copy it into your assigned lane directory and modify that copy ONLY. Do not edit the canonical tmp/sl101-nura/source/ported-source, preexisting devices-trunks source, shared pmbootstrap build/chroots, other lane files, or docs/sl101-nura-bringup.md. Do not commit/bulk-format unrelated dirty work. No SSH, live tablet actions, reboot, flash, package changes or replacing Mesa. Integration and hardware qualification belong to the coordinator after both lanes are reviewed. Existing other android-infra CI tasks do not authorize touching our port or committing dirty files.

Use installed project workflow if required: adopt/admit and bind the EXACT supplied OCP task ID, begin/checkpoint/submit typed result through ws-bridge agent_workflow and retain required independent review. Routine workflow setup is authorized. If no workflow contract applies, return an exact artifact/result reference. One project header is already supplied; do not add another. Do not claim filesystem access from composer text alone.

Deliver a patch against the immutable baseline, modified source copy, focused compiler/command tests exercising actual semantics and explicit rejection of unsupported inputs, short integration instructions and remaining limits. Use primary Grate/host1x source documentation when researching. Avoid stubs or silently claiming unsupported operations. Keep GPU state and compiler resource limits correct; validate before emitting commands.

Exact OCP task: SL101-GRATE-TEXTURE-20260930
Exclusive writable lane directory: /home/user/code/android-infra/tmp/sl101-nura/parallel/texture

Implement fragment texture sampling and sampler/resource emission required by typical wlroots GLES2 texture shaders. Own sampler, texture resource/format/state emission and TEX lowering. May edit your copy of fp/tgsi.c for texture lowering, fp IR/packing and supporting resource/state files. Do NOT implement generic arithmetic opcodes; state minimal interface requirements for arithmetic lane. Both lanes may edit separate copies of same files; produce small patches so coordinator merges deliberately. Validate texture coordinates, supported formats, filtering/clamp defaults, sampler binding, DMA/BO lifetimes, rejection paths and command layout. Start from current code, identify actual missing pieces, deliver practical initial supported subset, not a design-only response.
