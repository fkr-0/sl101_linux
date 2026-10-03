# SL101 genuine GPU/EGL work, revision 2

User-authorized re-dispatch on 2026-09-30. Goal: hardware shader execution and
truthful EGL window/compositor support, with archived implementation and device
evidence. A passing constant triangle remains the baseline, not final acceptance.

## Reconciled starting point

- The original texture and arithmetic conversations are fully synced in
  Chronicle. Both have a terminal assistant response explicitly reporting
  connector failure and no source edits. Their lane copies match r3 unchanged.
  Their stale `running` task state must be reconciled to `blocked_retriable`
  using that termination audit, then retried **under the same task IDs**.
- The project connector now supports `begin_agent_session`,
  `read_workspace_file`, and `run_workspace_command` on the real checkout.
  The advertised legacy `read_file` alias is absent: use workspace-scoped tools.
- Live Grate kernel, authorized SD CID and pixman labwc were checked. The last
  r5 GLES2 labwc probe still reports exit 139 and `Segmentation fault`.
  No crash stack has yet explained it.
- The current canonical source differs from r3 in six files, covering resource,
  screen, winsys and a libdrm dma-buf patch. A frozen 42-file current snapshot
  and SHA256 manifest are under `tmp/sl101-nura/gpu-egl-20260930-r2/`.
  Source presence does not prove which source built the r5 binary.
- Another browser-integration worker owns
  `tmp/sl101-nura/qualification/desktop-browser`. Preserve its claim and work.

## Lanes and ordering

| Lane | Task | Responsibility |
|---|---|---|
| Texture | `SL101-GRATE-TEXTURE-20260930` | TEX, sampler/resource state, supported texture semantics |
| Arithmetic | `SL101-GRATE-ARITHMETIC-20260930` | ALU, immediates, varying math, scheduling/resource limits |
| EGL | `SL101-GRATE-EGL-20260930-R2` | r5 crash reproducer, EGL/GBM fixes, reviewed integration, sole GPU-test owner |
| Review | `SL101-GRATE-GPU-REVIEW-20260930-R2` | Independent verdicts, hardware-evidence inspection, continuation supervision |

Texture and arithmetic implement in separate copies. EGL begins crash/resource
diagnosis independently, then integrates **reviewed** shader patches. The review
lane can inspect and review without reserving an implementation packet. Respect
the project's four active implementation workers and two reviewers; browser
capacity is not permission to exceed packet capacity.

Each lane writes only its dedicated subtree. The initial native dispatch round
has at most three attempts. Review is dispatched in a subsequent bounded round.
The native dispatcher injects the project header; catalog bodies omit it so
delivery contains only one `@projmgrauth` / `Set repo` header.

## Real continuation contract

Every phase must archive a patch/test or hardware-evidence delta, checkpoint,
and typed `abc-chain.phase-result` with exact task/packet correlation. If useful
work remains, request one same-scope continuation with `disposition: ready`.
The live `submit_phase_result` reconciles the derived packet into OCP. The
project's `operator_gate` and independent review remain mandatory: the authorized
review/supervision lane publishes the exact approved successor through
`resolve_runtime_opportunity`; native OCP admission/event handling owns delivery.
Workers can continue on that successor in-session when the legal packet
transition permits it. No new confirmation is needed for this authorized scope.

These are continuation instructions, not evidence that a successor already
exists. Inspect `derivedPacket`, `lifecycleReconciliation`, approval and canonical
task state before reporting chaining. Two identical no-progress attempts must
produce a new diagnosed method or a concrete blocker, not another repeated audit.

## Acceptance

1. Actual wlroots shader semantics pass numerical/texture readback tests.
2. The required EGL/GBM/window/image/dma-buf subset works with truthful caps,
   supported format/stride/offset/modifier checks, sync and correct BO lifetime.
3. GPU labwc runs real Wayland clients and a repeated textured/arithmetic
   composition workload for at least ten minutes without fallback, SIGSEGV,
   corruption, new GPU faults or resource growth.
4. Process-correlated GR3D/host1x submissions prove GPU execution, alongside
   pixels, frames, CPU/RSS and timings. Renderer strings alone are insufficient.
5. The prior pixman session is restored after every temporary compositor probe.

Only EGL owns live GPU tests. It uses the existing remote qualification lock,
verified SSH host key/device identity and new private candidate prefixes. Initial
compositor probe: 15-second limit with rollback installed before stopping the
exact discovered compositor. Longer workloads follow demonstrated progress.
No reboot, kexec, flash, eMMC, network restart, stock Mesa replacement or persistent
default changes. The private flashable snapshot is outside every lane's scope.

See `manifest.json` for exact prompt IDs/files. Durable starting evidence and
dispatch receipts belong in `tmp/sl101-nura/gpu-egl-20260930-r2/evidence/`.
