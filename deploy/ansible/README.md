# SL101 Ansible via Docker Compose

The workstation owns Ansible. The devices run no Ansible controller. Root
workspace, inventory, data and SSH directories are bind-mounted read-only.
The container runs without privileges, host Docker socket, or host networking;
only its Ansible cache is writable on the host.

## Inventory

| Target | IP | OS | Hostname | Verified archival SD CID |
| --- | --- | --- | --- | --- |
| sl101-nura | 192.168.23.106 | Alpine/postmarketOS | sl101-nura | 035344534c31323880ac79a543010300 |
| sl101-debian | 192.168.23.100 | Debian Trixie | sltwrpbootdebian | 03534453553332478030be3f6400b900 |

Sources: docs/sl101-0076-dontkmap-ab-20261109.md and
docs/sl101-debian-input-rollout-20261109.md. Each run checks live hostname
and physical CID before any privileged changes.

## Usage (repository root)

    mkdir -p deploy/ansible/data deploy/ansible/.state
    docker compose -f deploy/ansible/compose.yaml -f deploy/ansible/compose.nura.yaml build
    docker compose -f deploy/ansible/compose.yaml -f deploy/ansible/compose.nura.yaml run --rm deploy test
    docker compose -f deploy/ansible/compose.yaml -f deploy/ansible/compose.nura.yaml run --rm deploy check

Swap compose.nura.yaml for compose.debian.yaml to target Debian.
The default check only checks device identity (read-only); to preview
a full command cutover, set SL101_CUTOVER=YES.

    SL101_CUTOVER=YES docker compose -f deploy/ansible/compose.yaml -f deploy/ansible/compose.nura.yaml run --rm deploy check

Actual apply requires both explicit gates:

    SL101_APPLY=YES SL101_CUTOVER=YES docker compose -f deploy/ansible/compose.yaml -f deploy/ansible/compose.nura.yaml run --rm deploy apply

Never apply to a live desktop: the guard refuses if sway, sl101-sway
or labwc is running. No compositor restart, GPU lock, VDE change,
flash or boot manipulation is performed by Ansible.

## Canonical comma commands and hard cutover

Original user-facing shell sources are the existing device-config
usr/local/bin/sl101-* files in docs/. No extra alias manifest exists:
deploy/ansible/tools/render_public.py derives the public command namespace
directly from their filenames into /tmp/sl101-rendered, then rewrites known
command-to-command paths in the scripts and active Sway/labwc/desktop/service
configuration. The installer deploys the new names (e.g. ,browse, ,desktop,
,foot-launch), backs up old binaries to
/var/lib/sl101-deploy/legacy-bin, and REMOVES the old public filenames:
no compatibility symlinks and no prolonged dual namespace.

24 Nura and 15 Debian commands are in the current offline test surface.
Not all internal privileged entrypoints are migrated. In particular,
sl101-sway (the compositor with special file-capability constraints),
sl101-firefox-root and sl101-doom-root are internal dependencies that
must be separately verified and ported to a libexec boundary. The cutover
must NOT be interpreted as permission to delete arbitrary sl101-* files.
Test all Sway/keyboard/touch/desktop paths at postflight before calling
the deployment complete.

Molecule uses delegated localhost, two fake device roots, the REAL
command-install tasks, a second run (idempotence), and verification.
It never contacts a tablet. The host equivalent is:

    cd deploy/ansible
    molecule test -s default

## Kernel release blockade

The host-built dmafix1 is based on the productive .100 source/config.
Its build incorporated the ARM CMA alias patch and the generic direct DMA
initialization patch, but NOT the separately qualified Tegra VDE cached
CAPTURE v2 patch. The release is therefore NOT production-complete.

This host-only guard verifies the built module, not just source patches:

    python3 deploy/ansible/tools/verify_kernel.py --root work/sl101-prod-dma-init-20261110 --release 7.0.1-postmarketos-grate-dmafix1 --expected-dtb-sha 01fbb5a935e429c42dc5e2793049bbfc91ff3a6f73c15f2063e1fb0af1a289b0

It deliberately fails because the VDE cached_capture parameter is
absent from tegra-vde.ko.zst. A **new** separate combined release,
`7.0.1-postmarketos-grate-dmavde1`, has four host-applied source
patches (CMA alias, DMA-direct zero, cached CAPTURE v2 and async
semaphore), 587/587 matching modules and a complete archive.

Read-only combined-RC preflight (also usable in check mode):

    ansible-playbook -i deploy/ansible/inventory/hosts.yml deploy/ansible/playbooks/kernel-preflight.yml --check

The device-side read-only preflight is separate:

    ansible-playbook -i deploy/ansible/inventory/hosts.yml deploy/ansible/playbooks/hardware-preflight.yml --limit sl101-nura

The earlier RC2 one-shot test was inconclusive. As of 2026-11-11,
the complete four-patch dmavde1 candidate has been physically flashed to
.106's actual eMMC LNX slot and authenticated after a normal reboot.
This proves bootability, NOT GPU/CMA performance, video, suspend or
unconditional production safety; preserve the verified boot rollback.
No kernel staging/reboot/flash is included in the current playbooks.

## CI-only NuraLoumi 0.0.4-dev.2 stage for .106

The separate playbook 'playbooks/nuraloumi-stage.yml' is independent of
the unqualified public comma-command cutover. It does NOT change the
active session or boot. Latest 2026-11-11 hardware evidence confirms the
.106 kernel boots from its eMMC LNX slot, but the Alpine ROOT remains
microSD /dev/mmcblk1p1. Both identities are checked; do not confuse them.

Prepare only the exact successful GitHub CI musl artifact on the host:

    python3 deploy/ansible/tools/nuraloumi_ci_payload.py prepare \
      --nuraloumi-repo /home/user/code/nuraloumi \
      --out-root deploy/ansible/data/nuraloumi \
      --sha 6d4f7b2d728db3251d244bdebf38dc6e415856f5 \
      --run-id 42927406671

The tool invokes the sibling GitHub exact-run verifier and validates
all 24 binary ELF32 ARM hard-float files, the full tar manifest and
individual checksums before publishing in ignored data/nuraloumi/<sha>.
The CI source SHA, run ID, tar digest and manifest digest are pinned in
the reviewed inventory, not supplied merely by an untrusted JSON file.

Read-only identity + staging preflight, **tested successfully 2026-11-11**.
From the workstation, the existing SSH config's authenticated ControlMaster
may be reused without granting a new key to the controller container:

    export SL101_NURALOUMI_SHA=6d4f7b2d728db3251d244bdebf38dc6e415856f5
    export SL101_NURALOUMI_RUN_ID=42927406671
    ANSIBLE_SSH_ARGS='-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ControlMaster=auto' \
      ansible-playbook -i deploy/ansible/inventory/hosts.yml \
        deploy/ansible/playbooks/nuraloumi-stage.yml --limit sl101-nura --check

Expected recap is `changed=0, unreachable=0, failed=0`. In `--check`
mode all 24 executable copy tasks and the readiness-marker write are
explicitly skipped. The controller-only verifier and read-only target
identity, disk capacity and symlink checks still run. The current
approved benchmark-B kernel is `7.0.1-postmarketos-grate-dmavde1-minus-cma`,
and `/etc/os-release` identifies `ID=nura` (not `alpine`).

The Docker command remains available where the controller itself has a
working, independently authenticated SSH key or permitted SSH multiplex
transport. It does not automatically inherit the workstation's existing
SSH ControlMaster connection.

Staging-only write after explicit operator review (no activation):

    SL101_APPLY=YES SL101_NURALOUMI_STAGE=YES \
      docker compose -f deploy/ansible/compose.yaml \
        -f deploy/ansible/compose.nura.yaml run --rm deploy nuraloumi-stage

This installs binaries to /opt/nuraloumi/releases/<sha>/bin and verifies
remote SHA256 before marking CI-READY. It does NOT update current,
install an APK or key, replace /usr/local/bin binaries, restart a panel,
modify Sway/Mesa/WayVNC, or change the kernel.

The stage imports the **complete original CI tar** (not a local build):
all 24 ARMHF/musl executables plus config/share resources and original
documentation, cross-checked against the Git-reviewed tar SHA256. It
intentionally uses a versioned inactive release. A separate activation
playbook has its own explicit third approval gate:

    export SL101_NURALOUMI_SHA=6d4f7b2d728db3251d244bdebf38dc6e415856f5
    export SL101_NURALOUMI_RUN_ID=42927406671
    export ANSIBLE_SSH_ARGS='-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ControlMaster=auto'
    ansible-playbook -i deploy/ansible/inventory/hosts.yml \
      deploy/ansible/playbooks/nuraloumi-activate.yml --limit sl101-nura --check
    SL101_APPLY=YES SL101_NURALOUMI_STAGE=YES SL101_NURALOUMI_ACTIVATE=YES \
      ansible-playbook -i deploy/ansible/inventory/hosts.yml \
        deploy/ansible/playbooks/nuraloumi-activate.yml --limit sl101-nura

The activation tool atomically points /opt/nuraloumi/current at the
release's bin directory, installs all 24 canonical CLI names under
/usr/local/bin as links to the active current version, and preserves the
old current link plus the prior workspace-switcher executable. It then
restarts ONLY the NuraLoumi panel through the existing
/usr/local/bin/sl101-sway-panel hook using the live Wayland environment.
The playbook checks the real new /proc/PID/exe and all 24 symlinks.
Any failure enters a rollback block, restoring the old link, old
workspace switcher and old panel without touching Sway.

**2026-11-11 production-device receipt:** this exact latest CI run was
successfully installed and activated on .106: Ansible ok=35,
changed=2, failed=0. The final panel PID was 21781 with 8088 KiB
VmRSS, the compositor PID 1438 and WayVNC PID 1484 stayed unchanged,
all 24 binaries passed SHA256 and 24/24 dynamic dependency checks.
The previous release is still /opt/nuraloumi/releases/menu-dismiss-e4d6301.
These are device/process/linker checks, not an interactive UI/pixel
qualification of every surface. See
docs/sl101-106-nuraloumi-ci-ansible-20261111.md for provenance and
rollback. The separate playbooks/nuraloumi-rollback.yml is the
explicitly authorized, identity-guarded full manual restoration path;
do not execute it until requested.

## Remaining porting

Port verified Mesa/libdrm bundles, VDE-video/Cog processes, systemd vs OpenRC
ownership, keyd/seatd, hardware locks, and kernel/DTB+module staged deploy.
Keep independent historical scripts as rollback evidence until corresponding
Ansible roles and device postflight are verified. Device identity evidence
does not authorize an unsafe live graphics change.
