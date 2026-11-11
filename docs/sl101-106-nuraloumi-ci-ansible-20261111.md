# .106 NuraLoumi CI-only Ansible preparation — 2026-11-11

**Status: host-only preparation.** This work did NOT SSH, deploy, flash,
reboot or restart Sway/panel, change any kernel or eMMC/SD data, or
invoke the separately blocked comma-command hard cutover.

## Exact physical and CI contract

| Property | Reviewed requirement |
| --- | --- |
| Target | sl101-nura, user@192.168.23.106 (never .100) |
| Linux ABI | Alpine/postmarketOS ARMv7 musl |
| Internal eMMC CID | 7001004d4d43333247448d402a656e00 |
| microSD CID | 035344534c31323880ac79a543010300 |
| Linux root | /dev/mmcblk1p1, microSD |
| Running kernel | 7.0.1-postmarketos-grate-dmavde1 |
| Kernel boot source | The working 8-MiB eMMC LNX slot (not SD extlinux) |
| NuraLoumi source SHA | 6d4f7b2d728db3251d244bdebf38dc6e415856f5 |
| Alpine Actions run | 42927406671, successfully completed |
| Original CI tar SHA256 | b4b7f2d13b981b4494c1e2d09672eed975b355d398d1e435940ce412a7fdb1fb |
| CI manifest SHA256 | 78421682071e98ceaa706043ec52c434e2d6fc7e5eb6d572fd76b621d0f4674a |

All these release selectors and checksums are pinned in
deploy/ansible/inventory/hosts.yml. The physical device/boot evidence is
docs/sl101-two-device-boot-and-kernel-contract-20261110.md and
docs/sl101-106-dmavde1-flash-20261111.md.

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
| 'deploy nuraloumi-check' | Read-only SSH identity and Ansible check-mode preview |
| 'deploy nuraloumi-stage' with both gates | Only versioned copies to /opt/nuraloumi/releases/<sha>/bin; remote hash checks and CI-READY |
| Live activation | NOT implemented or authorized by this preparation |

There is no APK installation, ephemeral-key enrollment, kernel/boot/Mesa
mutation, Sway reload, WayVNC/keyd/init change or replacement of current.
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
