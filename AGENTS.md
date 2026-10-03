# SL101 Linux agent guide

Owns SL101 kernel/DTB integration, Grate Mesa, Nura userspace, boot/rootbind/SD tooling, browsers, audio/input, qualification and upstream preparation. NuraLoumi source belongs to its separate repository.

- Preserve the existing repository history, historical build setup and unrelated local changes.
- Read README.md, docs/MIGRATION-20261003.md and relevant qualification notes first.
- Keep generated binaries/rootfs/build trees, device backups, credentials and local state out of Git.
- Preserve historical evidence and schema identifiers. New operational paths use this repository root.
- Require exact target identity and artifact provenance before device mutation. Keep deployment dry-run-first and preserve rollback.
- Never run unattended suspend, force mem/deep, or bypass inhibitors over SSH. Physical supervision and a recovery route are required for real suspend qualification.
- Native EGL initialization does not prove correct pixels, acceleration, browser functionality or safe default promotion.
- Run `make test` and `make check` before handoff; tests must not mutate a live desktop/device.
- Coordinate packet/file ownership before concurrent writes. Only one lane may mutate the live SL101 graphics/session state.
- Pending pre-migration OCP tasks remain tied to android-infra. Old local paths are compatibility links; do not blindly redispatch them or reinterpret their authority.
