# .106 NuraLoumi CI-only Ansible preparation — 2026-11-11

**Status: host preparation and successful read-only .106 preflight.**
The first preparation did not access the device. On 2026-11-11 a subsequent
read-only check used the workstation's already authenticated SSH
ControlMaster connection. It did NOT deploy, flash, reboot, restart
Sway/panel, change any kernel or eMMC/SD data, or invoke the separately
blocked comma-command hard cutover.

## Actual read-only Ansible preflight receipt

Run from repository root, using the host's existing authenticated SSH
ControlMaster and strictly checked host key (rather than expecting the
isolated Docker container to inherit the mux session):

    SL101_NURALOUMI_SHA=6d4f7b2d728db3251d244bdebf38dc6e415856f5 \
      SL101_NURALOUMI_RUN_ID=42927406671 \
      ANSIBLE_SSH_ARGS='-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ControlMaster=auto' \
      ansible-playbook -i deploy/ansible/inventory/hosts.yml \
        deploy/ansible/playbooks/nuraloumi-stage.yml --limit sl101-nura --check

Verified receipt:

    sl101-nura: ok=14 changed=0 unreachable=0 failed=0 skipped=9

The checks confirmed the exact physical CIDs, SD root, Nura/musl ABI,
running minus-CMA benchmark kernel, more than 90 MiB free disk space,
and the pinned complete CI artifact. The active panel/current symlink
were not replaced. The read-only check found the existing
`/opt/nuraloumi` and `releases` parents use group 12345 and setgid mode
`2755`; the stage tasks were repaired to preserve these live-directory
attributes on a future write. This is preflight success, **not** hardware
qualification of the new binaries or permission to activate them.

## Exact physical and CI contract

| Property | Reviewed requirement |
| --- | --- |
| Target | sl101-nura, user@192.168.23.106 (never .100) |
| Linux ABI | Alpine/postmarketOS ARMv7 musl |
| Internal eMMC CID | 7001004d4d43333247448d402a656e00 |
| microSD CID | 035344534c31323880ac79a543010300 |
| Linux root | /dev/mmcblk1p1, microSD |
| Running kernel | 7.0.1-postmarketos-grate-dmavde1-minus-cma (benchmark B, NOT a production recommendation) |
| Distribution ID | nura (Nura edge; ARMv7 musl loader confirmed) |
| Kernel boot source | The working 8-MiB eMMC LNX slot (not SD extlinux) |
| NuraLoumi source SHA | 6d4f7b2d728db3251d244bdebf38dc6e415856f5 |
| Alpine Actions run | 42927406671, successfully completed |
| Original CI tar SHA256 | b4b7f2d13b981b4494c1e2d09672eed975b355d398d1e435940ce412a7fdb1fb |
| CI manifest SHA256 | 78421682071e98ceaa706043ec52c434e2d6fc7e5eb6d572fd76b621d0f4674a |

All these release selectors and checksums are pinned in
deploy/ansible/inventory/hosts.yml. The physical device/boot evidence is
docs/sl101-two-device-boot-and-kernel-contract-20261110.md and
docs/sl101-106-dmavde1-flash-20261111.md. The later
docs/sl101-106-minus-cma-deployment-20261111.md supersedes the older
kernel pin for the ongoing A-B-A benchmark. Ansible intentionally
refuses a subsequent kernel change until a new independent review.

## Staged source and integrity

The controller tool 'deploy/ansible/tools/nuraloumi_ci_payload.py prepare'
invokes the NuraLoumi GitHub exact-run verifier, which confirms successful
CI on main and downloads the exact SHA-specific Actions artifact. The local
importer verifies all SHA256 file digests, tar member names/types, exact
declared 24 binaries, ARM hard-float ELF32 class and original manifest.
The downloaded APK's development signing key is NOT installed.

Only after complete verification is the new payload published to the
Git-ignored 'deploy/ansible/data/nuraloumi/<sha>' directory. It contains
release/bin (24 executables), the original release/MANIFEST.txt,
SHA256SUMS.bin, ELF-AUDIT.txt and CI-PROVENANCE.json.

Ansible repeats local payload checks and compares pinned tar/manifest
SHA256 against the Git-reviewed inventory. It then checks the remote
physical hostname, both MMC CIDs, exact root, OS and running kernel
before any remote write.

## Effects and rollback policy

| Operation | Effect |
| --- | --- |
| Controller prepare | Downloads from GitHub to local ignored data only; no tablet |
| 'deploy nuraloumi-check' | Read-only SSH identity, exact pinned CI checks, capacity/parent safety; copy tasks explicitly skipped |
| 'deploy nuraloumi-stage' with both gates | Only versioned copies to /opt/nuraloumi/releases/<sha>/bin; remote hash checks and CI-READY |
| Live activation | NOT implemented or authorized by this preparation |

There is no APK installation, ephemeral-key enrollment, kernel/boot/Mesa
mutation, Sway reload, WayVNC/keyd/init change or replacement of current.
The real installation parents use setgid and a device-specific group;
staging deliberately preserves their existing group and mode rather
than normalizing them to root:root 0755.
Files under /opt/nuraloumi/releases/<sha>/bin are inert until the operator
explicitly authorizes promotion. The existing launcher reads
/opt/nuraloumi/current/nuraloumi-panel, so any future activation must
atomically point current at the release's bin directory, preserve the
old target and qualify the separately configured Sway workspace switcher.

## Required gates

1. Complete offline Python/unit, Makefile check/test, syntax, Ansible
   idempotence and fake-device no-mutation tests.
2. Confirm .106 health, physical identity, usable sudo, SD free space and
   known-good recovery route; never assume successful eMMC flash alone
   qualifies userspace or APX recovery.
3. Run read-only nuraloumi-check first, then explicitly approve
   nuraloumi-stage. On changed kernel, eMMC/SD identities, or root source:
   stop and review the inventory, never bypass the assertion.
4. Qualify the staged binary set on actual Tegra20: no SIGILL, panel
   renderer truth, Cairo/wl_shm, files/viewer, XDG/open-with, keyboard,
   touchscreen, workspace picker, memory/CPU and recovery.
5. A **separate** reviewed promotion and rollback plan is mandatory
   before touching /opt/nuraloumi/current or /usr/local/bin.

The CI Alpine APK is currently development-signed with an ephemeral
per-run key. This playbook stages the CI tar's verified binaries rather
than weakening APK trust or silently enrolling its temporary key.
