# Migration from android-infra

The existing GitHub repository `https://github.com/fkr-0/sl101_linux` is the canonical home for non-NuraLoumi SL101 Linux work. Its original tracked contents and Git history are preserved. The pre-existing untracked `sl101/` directory is also preserved and ignored, not silently published.

Moved: SL101 scripts/tests/fixtures, device Linux/graphics/browser/session documentation, upstream EC/DTB patches, and all `tmp/sl101*`, `work/sl101*`, and `state/sl101*` entries present at migration. NuraLoumi source remains in its own repository. The integration document mentioning NuraLoumi remains here because it records device graphics qualification.

Android fleet identity, inventory and generic ADB/Android tooling remain in android-infra. Its SL101 paths are relative compatibility symlinks to this sibling checkout, allowing existing commands and admitted workers to finish. These links are a migration bridge, not duplicate owned source. Clone both repositories as siblings if using those legacy entrypoints.

`work/migration-20261003/manifest.json` records every moved entry, original inode, hashes for top-level files and compatibility links. Directory inode preservation proves same-filesystem moves; existing nested artifact manifests remain unchanged. `android-infra.bundle` preserves source Git history; `sl101-working-tree.patch` preserves the two dirty SL101 script diffs. Historical logs/receipts retain original paths and project IDs.

The extracted preflight script and test use an unchanged copy of `android-infra/src/android_infra/runner.py` (source attribution retained here). The helper namespace and historical JSON schema identifiers intentionally remain compatible.

Already dispatched tasks retain their original android-infra packet/ownership bindings. Future tasks should resolve `sl101_linux` and use this root. Do not move in-flight packets or replay mutating prompts merely to rename their project.

This migration changes host workspace paths only. It does not deploy, flash, reboot, modify live desktop configuration, fork upstream projects, or publish files to GitHub.
