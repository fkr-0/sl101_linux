# SL101 Linux FBL03 native DP2 revision — 2026-11-03

OCP follow-up: `SL101-LINUX-03-DP2-NATIVE-SEMANTICS-20261103-9F3EFD`; exact original workflow packet `efeda9fb-85ae-4857-b29f-5d511d22d045` (opportunity `admitted-fd6887e71839252b53f66eea`). Independent review originally returned `request_changes`: the original Python tests only searched patch text and did not execute the compiler lowering.

## Hash-pinned source and patch order

| Input / output | SHA-256 |
| --- | --- |
| Current shared Mesa tgsi.c, **not modified** | `946541e9a38878317ab3c04af9997c7b2a6cca828bb78d9f93cbef448f5ac3a8` |
| Previous lane03 rebased-base.c | `2f5f5ebc6a582fe9205f757fb43b79c1150ba780eb09d534bfd936f3c6ea276f` |
| 0012-grate-fp-frc-dp3-dp4.patch | `069e06e2749997afe2cda662a666ae1e3f9435ea31d7f4ef94177bbdfff8f52f` |
| 0037-grate-fp-dp2.patch | `78bc63f2a62adf36c6de1faab68d9e6b2fe82b4083dc0246c0fe5a72766d53da` |
| Isolated source after strictly applying 0012 then 0037 | `514bfd76e0578c6e5a673f0a218dbe6a63b2db9416ea1b99f62924a1ee024b35` |

Both `git apply --check` and `git apply` succeeded **in order** on the isolated historical rebased source. Attempts against current shared Mesa source failed without any modification; see `work/fbl-revisions-20261103/03-dp2-native-semantics/logs/0012-grate-fp-frc-dp3-dp4.patch.check.log` and `.../0037-grate-fp-dp2.patch.check.log`. This matters for lane06: the patches cannot be replayed blindly onto current build state. Lane06 must own series/build integration and must pin/verify the compatible baseline or rebase explicitly. This revision **does not** modify series or shared build source.

## Host-native lowering coverage

`work/fbl-revisions-20261103/03-dp2-native-semantics/run_native.py` compiles a host-native C executable with Mesa Grate compile definitions and includes, directly including the **actual 0012+0037 patched** `tgsi.c`. The `test_dp2.c` harness invokes native `fp_emit_dp2` and inspects emitted ALU/PSEQ structures. The original FRC/DP3/DP4 tests are retained. Checks include:

- Two independent dot terms, `x*x + y*y` in MUL then MAD order (not a four-component DP4); swizzled operands, negated and absolute source modifiers; explicit reference scalar expectations used as examples, while emitted register selectors/flags are independently asserted.
- Destination X-only and XY/XYZW writemasks, empty mask, TEMP destination/source overlap with final MOV protection, scratch exhaustion with a closed failure, unsupported two-varying row conflict, and invalid source count.
- Host runner output: **PASS: 14 grate FRC/DP lowering structural tests**. Final output retained under `logs/native-replay.log`; an intermediate incorrect harness assertion failed during development and was corrected before final verification. This is an executable C lowering regression, **not** an emulator executing the numerical output, full Mesa shader compile/link, or GPU pixel test.

The tracked `tests/test_sl101_fbl03_fp_dp2.py` runs this native harness when the private isolated fixture exists; a checkout without it explicitly skips the native case. Such a skip is **not proof** of lowering. A portable committed fixture/harness is still needed before reproducible CI qualification, requiring a scoped packet amendment if file paths beyond the original ownership are needed.

## Gates and unresolved evidence

- `make test`: 224 tests passed on final rerun (exit 0), including compiled native harness (exit 0), log in private `logs/make-test.log`.
- `make check`: passed (exit 0), log in `logs/make-check-final.log`. Final test output in `logs/make-test-final.log`.
- No live device, SSH, compositor/session, GPU raster, or default acceleration changes. The production software-rendered recovery path remains untouched.
- GPU pixels, Skia Ganesh shader inventory and target compatibility remain **unverified**; no live qualification or deployment is authorized by this revision.
- Review remains mandatory; no self-approval. Lane06 owns patch-series/build handoff. Record integration baseline and patch hashes above before any downstream work.

## Continuation: portable native fixture and review scope (2026-11-03)

OCP task `SL101-LINUX-07-DP2-PORTABLE-HANDOFF-20261103-E8AFAD`; continuation packet `a9186341-9d63-4065-bf21-7453061f854e` (opportunity `admitted-67490d36eaf5c473d4a90f47`). Original packet `efeda9fb-85ae-4857-b29f-5d511d22d045` remains blocked; original artifacts, commits `86f259a` and `160491b`, original negative current-source replay and native 14 cases are preserved. The original report was retained; this is an additive continuation.

Tracked source/harness: `tests/fixtures/sl101-fbl03-native/{rebased-base.c,grate_compiler.h,fpir.h,test_dp2.c,manifest.json,README.md}`; strict runner: `scripts/sl101-fbl03-native-qualify.py`. The SHA-256 manifest identifies sources, patch order and expected output. The local historical rebased source is now committed, so the lowering replay no longer requires private `work/` sources. **The Mesa Grate configured Ninja build used to supply host compile flags still needs independently reproducible, pinned external preparation (lane06); a pristine checkout alone cannot perform the host build.** The historical source rebasing lineage predating `rebased-base.c` likewise remains incomplete; neither is represented as reconstructed provenance.

The explicit native command is `python3 scripts/sl101-fbl03-native-qualify.py --mesa-build build/mesa-grate-clean/mesa-25.0.7/builddir`; failures and missing inputs return nonzero. Optional Python unittest skips never count as native qualification. C assertions inspect emitted instructions, not numerical GPU execution, compiled shader correctness, or pixels.

## Independent review revision: inherited NDEBUG

OCP task `SL101-LINUX-10-DP2-ASSERTIONS-REVISION-20261103-5AAA09` resumes the **same** continuation packet after independent `request_changes`: the original runner inherited Mesa release `-DNDEBUG`, allowing all C `assert()` calls (including effectful lowering calls) to disappear while still printing PASS:14. The runner now appends `-UNDEBUG` after inherited compilation flags; the C fixture also fails compilation with `#error` if `NDEBUG` survives. A `--assertion-canary` mode injects a deliberately false native assertion; failed executables return nonzero, with core dumps disabled through `RLIMIT_CORE=0`. A real-Ninja-command wrapper in `tests/test_sl101_fbl03_fp_dp2.py` adds inherited `-DNDEBUG`: normal 14 cases must pass and the false canary must fail. Fixture SHA-256 was refreshed. This is **not** evidence of GPU pixels, shader linking, complete clean build reproduction, or hardware compatibility; configured Mesa headers/build remain a lane06 prerequisite. Independent approval is still pending.
