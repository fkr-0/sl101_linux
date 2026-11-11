# .106 NuraLoumi CI-only Ansible preparation — 2026-11-11

**Status: CI-only NuraLoumi installed and activated on .106 on 2026-11-11.**
The first preparation did not access the device. On 2026-11-11 a subsequent
read-only check used the workstation's already authenticated SSH
ControlMaster connection. A later, explicitly authorized full-suite
Ansible stage + activation has now completed successfully. It restarted
only the NuraLoumi panel, **not Sway**, and did not flash, reboot, change
any kernel or eMMC/SD boot data, alter Mesa, or invoke the separately
blocked comma-command hard cutover.

## Exact real-device installation receipt

- Latest GitHub main SHA checked on 2026-11-11:
  `6d4f7b2d728db3251d244bdebf38dc6e415856f5`.
  All three GitHub Actions workflows (CI, Alpine ARMv7/musl package and
  Debian ARMHF/glibc package) succeeded at that SHA.
- Production-target package: original *Alpine* 0.0.4-dev.2 GitHub CI tar
  from Actions run 42927406671, with pinned original tar SHA256
  b4b7f2d13b981b4494c1e2d09672eed975b355d398d1e435940ce412a7fdb1fb.
  The tar includes all 24 native executables, example config and
  share resources/documentation. No local build and no untrusted APK
  installation or temporary key enrollment was used.
- Native staging result: 26 successful Ansible tasks, zero failures.
  All 24 executable checksums verified by the target BusyBox
  `sha256sum -cw`; the full original tar digest matched on device.
  Every one of the 24 binaries loaded its shared-library dependency
  closure through the musl loader with **zero missing libraries**.
- Activation dry run: 20 successful tasks, `changed=0`,
  `unreachable=0`, `failed=0`.
- Real activation: **ok=35, changed=2, unreachable=0, failed=0,
  rescued=0**. All 24 `/usr/local/bin/nuraloumi-*` commands point at
  `/opt/nuraloumi/current/<name>`, and the active link points at
  `/opt/nuraloumi/releases/6d4f7b2d728db3251d244bdebf38dc6e415856f5/bin`.
- Independent postflight: `nuraloumi-panel` PID **21781** with
  `/proc/21781/exe` resolving to the exact new CI binary
  (SHA256 `467b183a8b1fc8c1d3eb3c3df6f3d109485b597edda13ec036283bd4784a6b33`),
  RSS **8088 KiB**. Sway PID **1438**, WayVNC PID **1484** stayed alive;
  24/24 installed checksums passed. The panel log reported live provider
  snapshots and no immediate exit.
- Rollback is saved: original release
  `/opt/nuraloumi/releases/menu-dismiss-e4d6301` remains intact.
  The old 1,269,476-byte workspace-switcher binary was copied to the
  root-owned `activation-backup` subdirectory of the new release,
  with `activation-rollback.json` recording the original active link
  and all 24 prior CLI states. The journal's `status=active` is
  authoritative; `CI-READY` is a staging-time receipt and its
  `ACTIVATED=false` field is NOT a current activation-status indication.

The physical user interface still needs interactive human hardware QA:
touch, keyboard, renderer labels, each popup/menu, file manager,
image viewer, Open-With, notifications, calendar, weather, media,
network feed, screenshot and WayVNC visibility. These cannot be
deduced from successful ELF/process checks alone.

### Manual recovery route

The separately gated `deploy/ansible/playbooks/nuraloumi-rollback.yml`
performs the complete manual rollback, including physical identity checks,
restoring the old CLI/workspace-switcher, restarting only the old
NuraLoumi panel and asserting the old /proc/PID/exe. **Do not run this
unless the operator actually requests rollback.**

    export SL101_NURALOUMI_SHA=6d4f7b2d728db3251d244bdebf38dc6e415856f5
    export ANSIBLE_SSH_ARGS='-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ControlMaster=auto'
    SL101_APPLY=YES SL101_NURALOUMI_ROLLBACK=YES \
      ansible-playbook -i deploy/ansible/inventory/hosts.yml \
        deploy/ansible/playbooks/nuraloumi-rollback.yml --limit sl101-nura

The activation playbook also automatically invokes the same helper and
relaunches the previous panel if its new-panel health check fails.
Never discard the stored activation-rollback.json or the backed-up
workspace-switcher until interactive qualification has been accepted.

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
| 'deploy nuraloumi-stage' with both gates | Versioned full CI archive (24 binaries + resources), remote hashes and CI-READY; no live desktop change |
| `nuraloumi-activate.yml` with three explicit gates | Atomic active-release switch, 24 CLI symlinks, single-panel restart, postflight and automatic rollback on failure |

There is no APK installation, ephemeral-key enrollment, kernel/boot/Mesa
mutation, Sway reload, WayVNC/keyd/init change or system-wide renderer swap.
The installation parents use setgid and a device-specific group; the
staging tasks preserve their existing group and mode, rather than
normalizing them to root:root 0755. The activation playbook DID update
`/opt/nuraloumi/current` and all 24 `nuraloumi-*` CLI links explicitly,
following prior preservation and with an automatic rollback path.
The existing Sway workspace-switcher invocation at `/usr/local/bin`
now follows the current CI release.

## Required gates

1. Complete offline Python/unit, Makefile check/test, syntax, Ansible
   idempotence and fake-device no-mutation tests.
2. Confirm .106 health, physical identity, usable sudo, SD free space and
   known-good recovery route; never assume successful eMMC flash alone
   qualifies userspace or APX recovery.
3. Complete read-only NuraLoumi preflight and exact CI package staging.
   Both PASSED, including on-device 24/24 SHA256 and musl dependencies.
4. Run the separately approved activation playbook and validate live PID,
   /proc/PID/exe, CLI links and rollback. PASSED with Sway untouched.
5. Remaining: interactively qualify the actual pixel output, renderer
   truth, Cairo/wl_shm, files/viewer, XDG/open-with, keyboard, touchscreen,
   workspace picker, network, memory/CPU stability and recovery on device.

The CI Alpine APK is currently development-signed with an ephemeral
per-run key. This playbook stages the CI tar's verified binaries rather
than weakening APK trust or silently enrolling its temporary key.
