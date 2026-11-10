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
absent from tegra-vde.ko.zst. A release must pass this gate AND on-device
boot/input/video/pixel qualification before it may become the default.
No kernel staging/reboot/flash is included in the current playbook.

## Remaining porting

Port verified Mesa/libdrm bundles, VDE-video/Cog processes, systemd vs OpenRC
ownership, keyd/seatd, hardware locks, and kernel/DTB+module staged deploy.
Keep independent historical scripts as rollback evidence until corresponding
Ansible roles and device postflight are verified. Device identity evidence
does not authorize an unsafe live graphics change.
