# GR3D serialization lane 02 — safety revision (2026-11-03)

## Decision: HOLD / NOT DEPLOYABLE

Independent review of original packet `ade186dd-f656-4ca6-8681-95b77b1b723c`
requested changes. The prior `ioctl` interposer has been replaced by a
**non-interposing, inert build sentinel**. It exports
`sl101_gr3d_fbl02_disabled() == -ENOTSUP` and deliberately does **not**
export `ioctl`, acquire a lock, inspect any pointer or claim that GPU work
has completed. Loading this candidate cannot supply GR3D serialization:
it MUST NOT replace a working desktop library or enable accelerated
defaults. This is risk removal, **not** completion of the original feature.

Original source path remains
`docs/sl101-device-config/usr/local/src/gr3d_serialize_fbl02.c`;
native adversarial evidence is in `fbl/02-gr3d-lock-protocol-test.c`.
No device, process environment or Mesa driver was modified.

## Review disposition

| Reviewer concern | Disposition / missing proof |
| --- | --- |
| Device, channel, GR3D identity | No ioctl interception until canonical device driver and channel identity are verified; ioctl nr `0x48` alone is not sufficient, including on non-GR3D DRM devices. |
| Completion ordering and ioctl ABI | Inert implementation has no premature unlock; target UAPI structure layout, successful wait-to-fence ordering, and `wait` semantics remain unproven. |
| fd dup, close, reuse and description lifetime | No caller-owned fd retained. Native adversarial pthread/fork/dup/close/reuse probes document kernel flock lifetime. Any future scheme needs an owned duplicate/open description and ordered cleanup. |
| Fork and reentrancy | No hook, mutex or global state in disabled candidate; full fork/recursive-ioctl protocol is not implemented. |
| Invalid userspace `syncpts` | No dereference at all, including arbitrary userspace pointers. A future design must copy validated ABI fields safely rather than blindly dereference. |
| Syncpoint wraparound | No threshold comparisons; new design needs an authoritative wraparound contract, not signed difference alone. |
| Interrupted waits, failures, bounded errors | Native mock checks that EINTR/ETIMEDOUT do not release a held lock; kernel completion and submission-failure-in-flight behavior are not established. |
| BO/fence lifetime | NOT proven by these tests. The disabled code does not manage BOs, and tests cannot establish GPU ownership. Never free an in-flight BO based on user-space heuristics. |
| Non-GR3D devices | No interposition at all, so matching request numbers cannot accidentally capture them. |

## Verification boundary

Run on **host only**:

    cc -std=c11 -Wall -Wextra -Werror -pthread -o /tmp/gr3d-fbl02-test fbl/02-gr3d-lock-protocol-test.c
    /tmp/gr3d-fbl02-test
    cc -std=c11 -Wall -Wextra -Werror -fPIC -shared -o /tmp/gr3d-fbl02-disabled.so docs/sl101-device-config/usr/local/src/gr3d_serialize_fbl02.c
    nm -D /tmp/gr3d-fbl02-disabled.so
    make test
    make check

The native tests exercise actual process and thread exclusion on distinct
open descriptions, keeping a lock across original fd close, dup and
reopening/reusing fd numbers, and retaining it after simulated interrupted
and timed-out waits. They **do not** exercise a real GR3D submit or prove
correctness of GPU completion, fence/BO lifetime, Mesa patch 0029 or the
actual Alpine/musl ARMv7 target ABI.

## Remaining acceptance gates and handoff

1. Establish and pin the Alpine/musl ARMv7 SDK and produce off-device
   ELF/ABI evidence; never build Mesa on the SL101.
2. Independently trace/verify GR3D OPEN_CHANNEL, submit, syncpoint and
   completion semantics on the authorized target, including GR2D negatives,
   channel reuse, wraparound, EINTR, submit failures and no-wait paths.
3. Design a single verifiable ownership protocol for every submission and
   fence/BO lifetime, including fd duplication, close/reuse, fork and
   reentrancy. Without a proven matching completion, fail closed.
4. Verify full GR3D state re-emission after inter-client lock acquisition,
   compare Mesa patch 0029 completion guarantees, and test two concurrent
   clients under separately authorized lane 01 handoff.
5. Require new independent source review and only then subsequent
   conductor-controlled hardware qualification. Retain pixman fallback.

No SSH writes, deployment, LD_PRELOAD activation, graphics/session mutation,
default promotion or public publication are authorized for this revision.
