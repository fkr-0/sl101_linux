# SL101 Ansible / comma-command cutover — independent security review

2026-11-10. **Host-only:** this review did not connect to or modify
SL101 tablets. Device `.106` remains physically unqualified after the
earlier DMA+VDE RC2 one-shot kexec handoff; no user-space migration
may be deployed as a workaround.

## Reviewed stack

Committed baseline `79dadfd`: `deploy/ansible` with Docker Compose,
Alpine Nura + Debian rootbind inventory, an exact-device identity
preflight, a renderer for canonical `,<command>` user CLI names, and
Molecule localhost fake-device verification.

The user has explicitly rejected a second alias manifest, permanent
`sl101-*` compatibility symlinks, or a two-namespace deployment.
Actual source files determine public names. Internal service/root
helpers must leave the public PATH altogether.

## Corrections in this review

1. The renderer's POSIX command regex was incorrectly escaped; bare
   `exec sl101-browse` was not migrated. It now recognizes explicit
   executable callsites while preserving `rc-service sl101-desktop`,
   process comm names, pidfiles and service identifiers.
2. Every renderer-produced script now carries a role-owned comment
   immediately below its shebang. The remote Ansible playbook refuses
   to overwrite a pre-existing comma command unless its contents carry
   a known managed marker, and refuses symlink or oversized-file
   collisions.
3. `apply` requires `SL101_APPLY=YES` and `SL101_CUTOVER=YES`.
   Ansible itself also refuses unapproved direct non-check invocations.
4. New controller tool `deploy/ansible/tools/validate_render.py`
   scans rendered command bodies, generated active configs and other
   checked-in active Sway/OpenRC/keyd/XDG configurations for legacy
   *executable invocations*. It fails before any remote mutation when
   callers still reference an old executable. Literal help heredocs,
   device logs and unit identifiers are not executable invocations.
5. Privileged/service helpers such as `sl101-cog-drm-root`,
   `sl101-cog-wpe-root`, `sl101-desktop` **must not be installed
   as public `,<command>`**. The new validator refuses them until
   their sources and dependent callers are moved to libexec; this is a
   path/privilege policy, not an alias manifest.
6. Validation happens both in the entrypoint and inside the Ansible
   playbook (delegated to the controller). Plain read-only `check`
   without `SL101_CUTOVER=YES` remains an identity-only preview.

## Current device cutover gate (deliberately RED)

For Nura `.106` the renderer currently produces 24 canonical script
names from 23 original templates plus `,renderer-status`, but the
review gate rejects 3 misclassified internals:

    sl101-cog-drm-root
    sl101-cog-wpe-root
    sl101-desktop

Therefore `SL101_CUTOVER=YES` with either check or apply must fail
until the internal service callers and libexec source paths are updated.
**Do not bypass this gate to publish `,desktop` or `,cog-wpe-root`.**

The compile/Ansible syntax tests and both Docker Compose override
configurations passed. The focused hard-cutover regressions passed
12/12; existing Ansible tests passed 7/7; the complete repository
test run (before adding the last private-helper gate test) passed
2091 tests with 3 skips. The Molecule default localhost scenario
completed syntax, preparation, converge, idempotence and verify
successfully, with idempotence showing zero changed files.

Limitations: Molecule is a **host-local fake-root qualification**, not
evidence of tablet runtime, remote file ownership, actual installed
binary parity, physical device recovery, or WPE/Grate pixel correctness.
The full hard cutover remains intentionally blocked.
