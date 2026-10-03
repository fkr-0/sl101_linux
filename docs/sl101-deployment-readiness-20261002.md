# SL101 deployment readiness — 2026-10-02

**Decision: retain the existing pixman desktop. GPU-default deployment is not
ready.** The private SD image is available for a controlled boot test on this
already-provisioned tablet, with the Debian spare available for recovery; it is
not a fully qualified or stock-device installation.

## Fresh verification

SSH at `192.168.23.106` responds. Kernel is `7.0.1-postmarketos-grate`; SD CID
matches `035344534c31323880ac79a543010300`. labwc PID 32231 still has
`WLR_RENDERER=pixman`. NetworkManager and sshd report started; battery reports
100%. No display, touchscreen, audio or Bluetooth physical retest was performed
in this review. No compositor switch, flash, reboot or default change was made.

The staged candidate-2 library hash matches its reviewed artifact:
`ad2843140258073cb435c21ca34621fe100ed15effaaccb63608082612db0ff9`.
The candidate archive also matches its declared SHA256:
`176144b95f9a36c1cab519c84b9eccefd194fbec71d4188ca4881006a58186ea`.

## Actual implementation progress

- Texture lane added TEX/sampler/resource-state code and an offscreen texture
  discriminator. Its host texture-contract test passes again in this review.
- Arithmetic lane added MOV/ADD/MUL/MAD lowering, FP20 immediates, modifier
  packing and fragment uniform handling. Fresh FP and vertex packing tests pass.
  The supplied test runner executes the two packing suites, not the separate
  TGSI-lowering test. These results do not establish device shader correctness.
- EGL lane captured r5's NULL-call SIGSEGV through
  `st_create_texture_sampler_view_from_stobj`, added sampler-view lifecycle
  callbacks, built a musl ARMv7 diagnostic library and removed a build-host
  RUNPATH following independent review.
- The independent reviewer permitted candidate-2 **only for bounded diagnostic
  staging**, explicitly excluding a native phase approval or texture/EGL/GPU
  acceptance. The candidate deliberately does not integrate the texture/ALU
  implementations.

## Deployment blockers

1. **Device texture test fails.** Candidate-2's EGL probe returns 5 with
   `FAIL: nearest/spatial/alpha readback mismatch`. All four sampled positions
   are yellow (`255,255,0,255`), so renderer/version strings do not prove texture
   sampling. See the archived probe stdout/stderr and run record under
   `tmp/sl101-nura/gpu-egl-20260930-r2/egl/evidence/`.
2. **GPU compositor jobs time out.** The candidate-2 headless labwc run records
   `tegra_drm_sched_timedout_job` for its process and GR3D hardware resets.
   Its GDB exit code 0 and empty GDB output are not a successful compositor test.
   An earlier memory-controller texture-read decode error also appears in the
   probe record; do not infer a precise cause from that message alone.
3. **Shader review findings remain unresolved in the current source.** The
   arithmetic candidate still puts embedded immediate words in the order
   challenged by the independent reviewer and maps every fragment varying to
   `LINK_SRC(1)`. Both lane sources retain advertised shader limits that require
   reconciliation with compiler/resource limits. The final texture upload-format
   path also lacks archived hardware proof. Host tests alone cannot close these
   findings; the immediate test currently encodes the same disputed word order.
4. **There is no reviewed combined candidate or endurance evidence.** No passing
   combined texture/ALU pixels, required dma-buf/window interoperability,
   accelerated ten-minute client workload, process-correlated GPU benchmark,
   or no-fault/no-leak compositor run has been archived.
5. **Workflow closeout is incomplete.** All four GPU tasks remain `running`, with
   empty canonical result and checkpoint references. Local source/test/review
   artifacts are real progress, but typed phase completion, independent final
   approval and result-derived successor publication are not established.

## SD image status

Fresh SHA256 of `tmp/sl101-nura/flashable/sl101-nura-adhoc-20260930.img` matches
the original manifest:
`fedd69cdd01093c9ac66b0bad723fe418e11be07db847267fab2f8a4f36bc59d`.
It is the private 4 GiB pixman/foot/NetSurf image, not a new accelerated build.
It retains Wi-Fi credentials and SSH identity; do not publish it.

Its manifest still lists physical flash/readback, cold boot of this image,
pixman startup on the internal 6.18.45 kernel, touch-corner mapping and visible
NetSurf use as pending. Running labwc now on RAM-booted Grate does not establish
cold-boot desktop support on that internal kernel. The SD alone does not install
the internal boot path on a stock SL101. See `sl101-nura-flashable.md`.

## Next deployment gate

Resolve the source-review defects with independent tests; review and integrate
the shader lanes into one private musl candidate. First qualify offscreen
varying arithmetic, texture/alpha and real EGL window swaps, then bounded
compositor tests under the existing device lock with pixman rollback. Promote
only after the real-client endurance and GPU-submission gates pass. Do not
repeat the already-failing diagnostic candidate as a default desktop.

Separately, boot-test the existing SD image while retaining the Debian spare,
and record network, desktop, touch and browser results before calling it a
qualified recovery deployment.

Operator snapshot at review start: global queue 40 (40 runnable); generating 0,
ready 3, error 0, waiting 17, complete 0. Four live windows contain 1–18 tabs
(configured 17/window, 68 total); rate 21 operations/5min versus target 300,
typed state `underrun`. Admission is blocked by resource-health policy.
Interval dispatch/enqueue/chain/legacy-prolong flow counters are unknown;
no dispatch was requested or performed by this review.
