# SL101 Tegra20 Grate: GLES2 required-feature audit (2026-11-02)

**Task:** `SL101-LINUX-20261102-SL101-GLES2-REQUIRED-FEATURE-AUDIT-20261102-E02458`
**Verdict:** **NO-GO for GLES2 conformance / accelerated browser default**. ESSL 1.00 context creation is experimental; it neither proves GLSL ES 1.00 completeness nor rendered pixels.
**Boundary:** read-only inspection of the **live, concurrently edited** generated Mesa 25.0.7 tree; source observations are an instant snapshot, not an integrated, frozen release. No driver, patch, build script, hardware, package, or runtime-default change from this audit.

## Evidence and repeatability

- Mesa tree: `build/mesa-grate-clean/mesa-25.0.7/`; driver `src/gallium/drivers/grate/` within that tree. The root `build/` tree is untracked; **do not commit or overwrite it**.
- Actual Mesa opcode enum: `src/gallium/include/pipe/p_shader_tokens.h:349-532`. No invented `TGSI_OPCODE_DPH` or assumption that all TGSI opcodes must be supported.
- NIR -> TGSI translator: `src/gallium/auxiliary/nir/nir_to_tgsi.c:3878-4106`; `grate_program.c:327,563` calls `pipe_shader_state_to_tgsi_tokens` for both shader stages. `PIPE_SHADER_IR_NIR|PIPE_SHADER_IR_TGSI` advertised by `grate_screen.c:301-302`. Conversion is **not** semantic support in the Grate backend.
- `nir_to_tgsi.c:3890-3978`: lowers indirect fragment input dereferences; texture projectors/TEX arguments; indirect addressing subject to reported caps; `nir_lower_discard_if` lowers conditional demote to structured control flow; int/bool ops can lower to float. `nir_to_tgsi.c:2766-2787,3073-3096` can emit TXP/TEX/TXL/TXB and IF/ELSE/loop tokens. These remain subject to Grate's narrow dispatch.
- Host check: `tests/test_sl101_gles2_opcode_coverage.py` parses **current** C function bodies, verifies dispatch names against the *actual* Mesa 25 header, exercises negative fail-closed source assertions, and compiles legal ESSL 1.00 fixtures with system `glslangValidator` v16.4.0. It also checks that unextended `dFdx` fails (optional OES derivatives). This is **not** a Mesa NIR/TGSI execution or device pixel test.
- L1 `.ws-bridge/agent-checkpoints/SL101-LINUX-{01..12}*.json` are *worker evidence*, **not** proof that every submitted patch is presently applied. As inspected, live FP ALU dispatch is `MOV ADD MUL MAD MIN MAX`; live FP top-level SFU dispatch is `LG2 SQRT EX2 SIN COS`; live VP dispatch is `MOV ADD MUL DP3 DP4 DST SLT SGE MAX MIN SEQ SNE FRC FLR SSG MAD RSQ`. `FP RCP/RSQ/FRC/LRP/DP3/DP4/CSEL` and VP scalar expansion have separate worker patches/checkpoints but **not all live dispatches**. Integration/reviews already have their own prompts; this report does not supersede them.
- No EGL device, GR3D pixel readback, runtime shader traces, GPU hang tests, or conformance suite executed by this task. Status **source-present** never implies **hardware-verified**.

Legend: **S** = source/driver route present (not device-proven), **P** = patch or worker artifact only / pending integration, **M** = missing or explicitly rejected in current Grate source, **U** = source insufficient to establish end-to-end correctness, **O** = optional ES2 extension (not mandatory), **L** = legal ESSL 1.00 source validated by glslang. For rows containing multiple operations, status is the weakest relevant route.

## GLSL ES 1.00 → Mesa IR → Grate coverage matrix

| ESSL 1.00 construction / ES2 requirement | Mesa 25 NIR/TGSI path | Grate live FP / VP / state path | Status / obligation |
|---|---|---|---|
| Scalar/vector assignment, swizzle, +, *, chained MAD | float NIR ALU -> TGSI MOV/ADD/MUL/MAD (or lowering) | FP six direct ALU cases; VP MOV/ADD/MUL/MAD | **S/U**: supported dispatch, FP20 rounding and cross-EXEC lifetimes need pixels |
| Negation/absolute, scalar vec constructors, vector component selection | NIR ALU + src modifiers and scalarization | FP `fp_src_component` handles negate/abs; VP `tgsi_src_to_vp` modifiers/swizzle; FP immediates FP20 representability checked | **S/U**; nonfinite/precision range not qualified |
| Subtraction, division, reciprocal, sqrt, normalization, length/distance | FADD+neg, TGSI RCP/RSQ/SQRT, DP, MUL | FP RCP/RSQ/DP only **P**; SQRT SFU **S**; VP RSQ **S**, RCP **P**; special math requires independent validity | **P/U**; division not validated |
| min/max/clamp/saturate, abs/sign, floor/ceil/fract/mod | MIN/MAX, FRC, FLR, FSGE and lowering | FP MIN/MAX **S**, FRC **P**, other lowerings **U**; VP MIN/FLR/FRC/SSG **S** | **P/U**; must measure semantics and precision |
| mix/step/smoothstep | NIR flrp / compare, TGSI LRP or decomposed MAD | FP LRP separate patch **P**, FP comparison patch **P**; VP comparisons **S** | **P/U** |
| Dot/cross, reflect/refract; matrix and vector operators | NIR fdot3/fdot4 -> TGSI DP3/DP4 (translator lines 1468-72); multiplies/adds | VP DP3/4 **S**; FP DP3/4 patch **P**; may exceed GPR/packet or two-varying constraints | **P/U** |
| pow, exp, log, sin, cos, sqrt | NIR math -> TGSI EX2/LG2/SIN/COS/SQRT and lowerings | FP SFU five **S**; VP additional scalar patch **P**; 2-stage preop timing/FP20 **U** | **S/P/U** |
| float comparison == != < <= > >= and bool ops | NIR comparisons -> TGSI SLT/SGE/SEQ/SNE, bool->float; some ops may lower | FP comparisons/CSEL **P**, live default ALU rejects these; VP SLT/SGE/SEQ/SNE **S** | **P/M** in fragment |
| ternary ?: and if/else | NIR `bcsel` / TGSI CMP or structured IF/ELSE/ENDIF | FP CSEL/CMP **P**; no FP/VP IF/ELSE dispatch | **M** general dynamic control flow; compile-time folded branches only |
| for/while/do loops, break, continue, bool predicates | Mesa NIR control flow can emit TGSI BGNLOOP/ENDLOOP, IF/ELSE, BRK/CONT | Neither shader compiler dispatches control flow; static unrolling not a general proof | **M/U**, mandatory ESSL semantics with permitted loops; no need for every Mesa control opcode |
| discard / conditional discard in fragment | NIR discard/demote -> TGSI KILL or (IF + KILL); `nir_lower_discard_if` does not eliminate kill | `grate_tgsi_to_fp` has no KILL/KILL_IF or PSEQ kill implementation | **M (P0)**; GLSL fragment `discard` legal (**L**) |
| texture2D(sampler2D, varying.xy) | `nir_tex` -> TGSI TEX 2D | `fp_emit_tex` accepts only `TGSI_TEXTURE_2D`, sampler direct < 16, coordinate `TGSI_FILE_INPUT` | **S/U** for simple 2D; sampler pixel correctness hardware-dependent |
| texture2D(sampler2D, computed expression), texture2DProj | computed NIR tex coord -> TGSI TEMP; projector TXP or lowering | `fp_emit_tex:1037-1044` rejects TEMP coords; TXP unsupported; source-level expression legal (**L**) | **M (P0)**; computed-coord follow-on already planned separately |
| textureCube / samplerCube / cube textures | NIR cube `tex` -> TGSI texture target cube | `fp_emit_tex` requires 2D; sampler-view target `PIPE_TEXTURE_2D` only; `max_texture_cube_levels=16` advertised | **M (P0)**; legal (**L**), mandatory ES2 cube support |
| Mipmap filtering, texture images at levels > 0, GL texture completeness | Gallium sampler min_mip_filter and sampler_view levels | `grate_create_sampler_state:406` rejects all mip filtering; `grate_create_sampler_view:485-486` requires both levels 0 | **M (P0)**; ES2 2D mipmapped minification path required |
| Sampler wrap repeat, clamp, filtering nearest/linear | Gallium sampler descriptors | REPEAT/CLAMP_TO_EDGE, NEAREST/LINEAR **S**; `MIRRORED_REPEAT` rejects in `grate_sampler_wrap_supported` | **M (P0)**: ES2 `GL_MIRRORED_REPEAT` is core |
| Color textures RGB/RGBA and required texture/renderbuffer formats | Gallium pipe formats through `is_format_supported`, `grate_pixel_format` | formats exist in resource mapper; live sampler views only RGBA/XRGB; A8/L8/LA8 patch **P** (extensions/util formats vs core distinctions apply) | **U/P**: core format upload/render path and texture completeness need verification |
| Uniform scalars/vectors/arrays, dynamic uniform indexing | constant loads, TGSI CONST + optionally indirect | FP `FP_UNIFORM_COUNT=32` **scalar** = **8 vec4**; ES2 minimum **16 fragment vectors**. VP 144 vec4 cap vs ES2 minimum 128; VP indirect constant cap=1 but `tgsi_src_to_vp` reads `Index` without `Indirect` | **M (P0)** guaranteed fragment resource floor; **U/P0** VP indirect addressing |
| Attributes (min 8), varyings (min 8), indices and linkage | shader inputs/outputs via TGSI declarations | VS 16 attribute slots; FP 16 TRAM rows, input <15, maps vertex export input+1. VS **one attribute and one uniform index per instruction** (`vp_validate_fetches:338-378`) | **S/U** for direct single-fetch; **P0** needs multi-source lowering and varying row/cross-EXEC qualification |
| FP temporaries / multi-expression assignments, values across EXEC | TGSI TEMP, CSE/copy-prop/reallocation | `FP_GPR_COUNT=8` scalar = **two vec4 temps**, pending texture aliases; fixed10 TEX-result GPR lifetime known unreliable from comments | **U/P0**: complex legal shaders can fail or silently miscompile |
| gl_Position, gl_PointSize, gl_FragColor; gl_FragCoord, gl_FrontFacing, gl_PointCoord | NIR IO + TGSI semantics/system values | VP output masks and FP single color DW exist. No demonstrated complete per-built-in handling of POSITION/FACE/POINTCOORD; input linking assumes vertex export N+1 | **S/U** for basic position/color; **U/P1** for required shader built-ins and rasterizer/point behavior |
| vertex shader texture2D/textureCube | ES2 allows **0** vertex texture units minimum | `MAX_TEXTURE_SAMPLERS` vertex=0 | **Core minimum satisfied**; VS texture sampling not required with cap 0 |
| Highp vertex and at least mediump fragment precision; derivatives | GLSL precision qualifiers; FP20 fixed/floating, VP precision hardware | FP20 encoding and SFU are not quantized/accuracy verified; `fragment_shader_derivatives=false` | **U/P1** mandatory precision range/accuracy; derivatives **O**, optional GL_OES_standard_derivatives, not a P0 missing op |
| 2D FBO color render-to-texture, framebuffer completeness, readback | GL state tracker -> Gallium texture surfaces & clears | `grate_screen_is_format_supported:309-362` restricts combined bindings; pitch/tight-stride and format restrictions; framebuffer path present; no captured device pixels for multi-pass | **U/P0** render-to-texture and pixel correctness required, EGL creation insufficient |
| Depth test/write, depth16 attachment | Gallium depth-stencil-alpha CSO, GR3D DEPTH_TEST_PARAMS | `grate_create_zsa_state:635-657` emits depth compare/write; Z16 format mapper exists | **S/U** depth test source path, hardware FBO/clear/readback unqualified |
| Stencil8 attachment, stencil test/op/masks/ref, stencil-only clear | Gallium stencil CSO / stencil ref / GR3D | `set_stencil_ref` only stores ref; `grate_create_zsa_state` only sets depth test params; clear has TODO partial preservation at `grate_resource.c:551` | **M (P0)** stencil operations; ES2 stencil functionality required where attachment present |
| Blend enable/disable, separate RGB/alpha equations/factors, color mask | Gallium blend CSO -> fragment blend shader variant | replace/source-over/standard alpha/additive variants; other factors/equations and partial color masks rejected fail-closed (`grate_state.c:270-365`) | **M (P0)** full ES2 blending/state operations; independent blend reviewer owns first four variants only |
| Drawing primitive topologies, indexed elements, GPU synchronization | Gallium draw path and fences | L1 draw splitting/u32 fallback and async fence live; correctness still under independent read-only review; some unsupported cases return false | **S/U**; pixel/ordering/fence qualification required |
| Multiple color attachments / `gl_FragData[]` | OES_draw_buffers / MRT route | screen advertises `max_render_targets=8` but FP program comments one color DW and variant supports one RT | **O** for GLES2 MRT (not core). **P1 cap-truth bug** independent of conformance |
| dFdx/dFdy/fwidth; fragment texture LOD; 3D/array textures | OES_standard_derivatives / other GL extensions | advertised false; no FP handler | **O**, not ES2 minimum. Test verifies bare `dFdx` fails without extension. |

**Important scope distinction:** ES2 requires `GL_TEXTURE_CUBE_MAP`, `GL_MIRRORED_REPEAT`, legal GLSL ES 1.00 branch/loop/discard constructs, and documented resource minima. It does **not** require every TGSI instruction, shader subroutines, geometry shaders, vertex texture sampling above zero, OES derivatives, MRT, floating-point textures, or ES3 functionality. An optimizer could legally replace an opcode, but it must *prove semantic coverage* for arbitrary valid input, not just make one demo compile.

## Priority findings (separate confirmed failure from unknown)

### P0 — required functionality missing, false resource floor, or browser-blocking behavior

1. **FS uniform floor definitively too small.** `fp/fpir.h:18` fixes 32 FP20 scalar uniforms; `fp/tgsi.c:313-320` rejects beyond that; `grate_screen.c:263-270` reports 128 bytes = 8 vec4. GLES2 minimum is 16 fragment uniform vectors (64 floats / 256 bytes). This is not solved by merely changing advertised caps. Needs hardware storage, proven spill or alternative lowering, *not a cap bump*.
2. **Cube targets and mipmaps/core sampler state absent.** `fp/tgsi.c:1037` hard-rejects non-2D; `grate_state.c:383-427,483-495` rejects MIRRORED_REPEAT, mip filter, cube and nonzero levels. `grate_screen.c:178` independently advertises cube levels; this is a definite capability inconsistency.
3. **Fragment discard and arbitrary flow-control absent.** Current two dispatch switches contain no KILL/KILL_IF or IF/ELSE/BGNLOOP/ENDLOOP, though Mesa's header and NIR translator know these tokens. Pending independent follow-on tasks cover discard and control-flow; avoid reassigning their implementation. Validate variant stability and side effects before integration.
4. **Computed/projected texture coordinates rejected.** `fp_emit_tex` requires INPUT, but ordinary GLSL expressions produce computed coordinates (often TEMP) and may use TXP/lowered projector. Existing dedicated computed-texcoords worker prompt covers initial implementation; target additional dynamic TEX QA after it integrates.
5. **Stencil and full ES2 blending unimplemented.** Depth test is wired, not stencil tests/ops/ref write behavior; blend variants cover only a subset of mandatory equations/factors and force full RGBA masks. A failed state change cannot be silently treated as a valid draw.
6. **Backend source/fetch/register correctness can break legal shaders:** two FP vec4 temporaries; FP TEX aliases and same-EXEC re-sampling; GPR lifetime, MFU interpolation, two-varying row conflicts; VP instruction only one distinct ATTRIB and one distinct CONST fetch, and VP indirect uniform index is ignored despite advertising `INDIRECT_CONST_ADDR=1`. Assign a *separate* addressing/materialization review, not an unbounded opcode expansion.
7. **Pixel and GPU-fence correctness required for promotion.** A successful ESSL=100 context or LLVM/host syntax compilation proves nothing about fragment interpolation, texture swizzles, FBO round trips, blend output, CPU map wait ordering or GPU timeouts. Preserve the pixman/softpipe recovery image and independent review gates.

### P1 — false positives, incomplete coverage, fidelity and limits

- `max_render_targets=8` vs single emitted DW/MRT path; this is a false advertising hazard even though MRT itself is **optional** ES2.
- `get_shader_param` reports 1024 vertex instructions while `vp/tgsi.c:519` rejects at 255; conservative cap/genuine lowering needed, not an assertion that the ES2 spec mandates 1024.
- Shader built-ins `gl_FragCoord`, `gl_FrontFacing`, `gl_PointCoord`, `gl_PointSize`, array/varying indices and VS dynamic uniform addressing require actual IR fixtures and rendered results, not guessed mapping.
- Mandatory supported float precision ranges, fragment precision, overflow/underflow/NaN/±0, trigonometric error and interpolation rules have no comparative pixel evidence.
- Depth-only/stencil-only clears currently pack both parts (`grate_resource.c:551,586`), risking attachment contents. FBO completeness, renderbuffer combinations, texture readback, and depth/stencil regression tests are required.
- Sampler and format mapper can be ahead of live sampler-view validation: `grate_pixel_format` lists A8/L8/LA88 but live `grate_sampler_view_format_supported` does not. Worker 10 has a distinct patch, not a currently verified live route.

### P2 — optional features / performance after mandatory baseline

- Derivatives without OES_standard_derivatives, MRT/OES_draw_buffers, float/half-float textures, 3D/array textures, shader subroutines, vertex texture units above zero, ES3 features: **not** prerequisites for a truthful ES2 baseline.
- Further throughput/large-draw optimizations are secondary to pixel and fence correctness. Do not promote asynchronous draws based solely on throughput.

## Acceptance, tests and observed limitations

Run from the repository root:

    PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_sl101_gles2_opcode_coverage.py' -v
    make test
    make check

The host fixtures prove `discard`, `textureCube`, computed coordinates, projected sampling, vector builtins, conditional/loop, matrix operations, and dynamic uniform indexing are syntactically legal GLSL ES 1.00 with glslang. They **do not** show what Mesa's NIR/TGSI emits for each fixture; the current no-compiled-Mesa-harness restriction is explicitly recorded. Negative `dFdx` without extension verifies the optional-extension distinction; expected-negative static checks detect if paths become accidentally permissive or drift without audit update.

A subsequent *full* acceptance harness should compile each fixture through the **actual Mesa 25 state tracker / NIR-to-TGSI** (record TGSI token stream via `GRATE_DEBUG=tgsi` or a native host harness), then on Tegra20 compare deterministic framebuffers to softpipe/llvmpipe reference. Include success **and** shader-failure semantics; test 8, 16 and >16 fragment uniform vec4, 1/2/3 temporary vectors, two attrs in one VP op, dynamic uniform array indices, two distinct varying rows, 2D TEMP/TXP/cube samplers, mip levels and MIRRORED_REPEAT, fragment discard inside branch/loop, gl_FragCoord/FrontFacing/PointCoord, color masks and all ES2 blend/stencil ops, depth/stencil selective clears, FBO attach/completeness, sync/readback, GPU timeout and rollback.

**Strict release gate:** preserve known working software rendering; require patch-stack clean apply, ARM native objects, recorded actual TGSI per shader, correct pixel tolerance with reference images, GPU-hang soak, device logs and conformance subset. Do not mark as conformance based on glslang source acceptance, `make test`, clean EGL, or a rendering window.

## Non-overlapping follow-up execution plan

| Lane and ideal role | Exact write ownership (reserve before use) | Dependencies and acceptance |
|---|---|---|
| A: **FS uniform resource-minimum architecture**, GPU/compiler implementer | New, separately reserved uniform lowering / hardware register investigation; no shared `fp/tgsi.c` writes before FP independent review and integration reservation | Demonstrate shader using 16 independent FS uniform vec4 with correct pixels, no cap deception; reject safely if hardware cannot satisfy; highest priority |
| B: **ES2 core sampler cube/mip/mirror**, texture implementer | Sampler target/descriptors, mip chain, sampling; distinct patch/tests from worker 10's single-channel formats and computed-coordinate lane | textureCube six faces, per-mip level LOD, all ES2 min filters, MIRRORED_REPEAT, FBO sampling, CPU/reference pixels |
| C: **ES2 stencil + state matrix**, fixed-function specialist | Stencil GR3D state and selective depth/stencil clear, missing blending factors and color masks in new independent patches | Every GLES2 stencil function/op/mask and blend factor/equation/separate, attachment-preserving clear; do not overwrite worker 09 or blend review |
| D: **Indirect address + fetch materialization + builtin linkage**, shader compiler specialist | VP multi-attribute/uniform-fetch lowering, VS dynamic constants; FP builtin system values, varying/TRAM row glue; separate patch and IR regression fixtures | Two distinct ATTRIB, two CONST, dynamic array index, gl_FragCoord/FrontFacing/PointCoord, two varying rows; trace TGSI and compare pixels |
| E: **NIR/TGSI/pixel conformance harness**, verifier | Independent host IR fixtures and *non-mutating* device qualification evidence after integration; no runtime defaults or patches | Real Mesa lowering traces, positive/negative fixtures, reference pixels, fenced readback, hangs, failures and reproducibility; publish explicit NO-GO or GO with evidence |

**Already covered elsewhere—do not duplicate:** FP 01–06 and VP 07–08 reviews, blend/draw review, texture formats/caps review, held renderer integration, computed texture coordinates, fragment discard and shader control-flow prompts. Lanes A–D are *additional* mandatory coverage only after the appropriate owners release their paths.

## Source snapshot and working-tree safety

At the time of the source read, `grate_screen.c` already advertised ESSL 100, `grate_draw.c` contained large-draw/fence changes, and `grate_state.c` contained blend variants. `fp/tgsi.c` did **not** contain all six FP workers' dispatches; `vp/tgsi.c` lacked the separate scalar worker's cases. Worker 04/05 checkpoints were `needs_retrigger`. Treat this as a changing, non-atomic tree and let the independent integration task establish the admitted version. No generated Mesa file was edited by this audit.
