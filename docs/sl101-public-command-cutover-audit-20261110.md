# SL101: hard comma-command cutover — offline audit and gates

State: 2026-11-10. This is an **analysis and qualification tool**, not an
alternate alias manifest. All inventory is calculated by reading the
actual executable names in the two device configuration staging trees
and the Compose/Ansible public-source directories.

## Offline command

From the canonical SL101 checkout:

    python3 tools/sl101-public-command-audit.py --format markdown
    python3 tools/sl101-public-command-audit.py --format json
    python3 tools/sl101-public-command-audit.py --gate

The normal audit **never touches a device or alters files**. The third
command exits with code 2 whenever the hard-cutover gate is not met. It
also rejects symlink destinations, overlapping canonical aliases
within a target, non-comma names and dangling references to guessed
legacy entrypoints after removal.

The scan intentionally excludes historical Markdown prose, build trees
and binary blobs. It reads Sway/keyd/OpenRC/session configuration,
deploy scripts and the complete contents of public wrappers — including
suffixless shell scripts. Source filenames *are* the deployment
authority: **no YAML/JSON alias mapping exists or should be created**.
The report is computed evidence, not another source of truth.

## Current offline baseline (not a live-device claim)

Before migration the scanner sees:

| Source staging tree | Entries |
| --- | ---: |
| `docs/sl101-device-config/usr/local/bin` | 23 |
| `docs/sl101-debian-device-config/usr/local/bin` | 15 |
| `deploy/ansible/public/nura` | 1 |
| **Total** | **39** |

Of these, **38 carry legacy `sl101-` names**, one has the canonical
`,<command>` form. There are **592 textual name references**, counted
per target command (shared callers are reported for each target and
are not 592 unique source lines). Those counts can change as other
workers edit the repository.

The densest dependency clusters include `sl101-desktop`,
`sl101-chvt`, `sl101-browse`, `sl101-cog-wpe`, and
`sl101-audio-session`. A direct `mv sl101-* ,*` is not viable:
Sway, OpenRC, other launchers, and system entrypoints depend on their
present paths.

## Hard cutover design, not dual public aliases

1. Use file location to separate public programs from internal helpers:
   true CLI programs belong in `/usr/local/bin/,<command>`; internal
   service/supervisor binaries should move to `/usr/local/libexec/`
   (and must not accidentally become public comma wrappers). **Review**
   `sl101-desktop`, `sl101-chvt`, `sl101-kms-run` and `*-root`
   individually. A filename under `/usr/local/bin` alone proves PATH
   visibility, not intended end-user semantics.
2. In the checked-in deployment sources, construct only the new
   canonical filenames. Rewrite every Sway, OpenRC, keyd, Cog,
   desktop-entry and shell caller to the final paths in the same
   transaction. Do not install an indefinite parallel `sl101-*`
   namespace, compatibility symlinks, or a separate alias table.
3. Before `apply`, verify target hostname, immutable SD CID and
   kernel/module provenance; ensure rollback contains **all**
   replaced binaries and configurations. Stage and verify before
   switching launcher references; if a reference is missing, fail
   before stopping a running desktop. No automatic DRM/KMS or
   kernel reboot from the general deploy.
4. After a targeted, physically recoverable cutover, execute the
   source-tree audit with `--gate` and separately inspect the live
   `PATH`, `type -a ,<command>` and absence of **old public**
   commands. Commit only the clean check/diff state. Program source
   filenames themselves are the declarative inventory.
5. Ensure repeat `ansible-playbook --check --diff` reports no changes
   and Molecule covers idempotency, collisions, stale live-configuration
   references, removal of old PATH files, and rollback.

The audit is deliberately fail-closed on old *filename* sources and
references inferred from new comma names. It cannot prove dynamic
command assembly, generated configs outside this repository,
actual device PATH contents, or that a root helper is safe to expose.
Those require additional review when the device has recovered.

## Post-kexec safety boundary

After the RC2 `dmafix1` + VDE one-shot handoff, `.106` was not
reachable by ARP/SSH. Treat the boot as **unconfirmed / presumed failed**
until a physical screen/serial examination says otherwise. No
Ansible migration, compositor restart, package installation, or browser
test is authorized by this document while the tablet is unreachable.
The internal stock eMMC boot path was not overwritten.
