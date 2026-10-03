# Linux on ASUS Eee Pad Slider SL101

This is the existing `fkr-0/sl101_linux` repository, extended with the SL101 Linux work extracted from `android-infra` on 2026-10-03. Its original Git history, `Makefile`, `build_kernel/`, `README.org`, and local `sl101/` tree are preserved.

## Current work

- Kernel/device-tree integration and boot provenance: `docs/sl101-kernel-coherence.md`, `docs/sl101-kernel7-consolidation.md`.
- Nura bring-up, SD deployment and rootbind: `docs/sl101-nura-bringup.md`, `docs/sl101-rootbind-phase-bc.md`.
- Grate Mesa/EGL qualification: `docs/sl101-working-egl-20261003.md` and `docs/sl101-egl-visual-regression-20261003.md`.
- Firefox and Cog/WPE browser environments: `docs/sl101-firefox-debian-20261003.md`, `docs/sl101-cog-wpe-20261003.md`.
- Audio, keyboard, remote control and system hygiene: the corresponding `docs/sl101-*` files and directories.
- Upstream patch preparation: `docs/upstream/`.

NuraLoumi's implementation remains in `/home/user/code/nuraloumi`, a separate repository. Its SL101 graphics integration evidence belongs here.

## Development

Run `make test` for the extracted SL101 unit tests. `make check` checks Python syntax without contacting hardware. The original kernel Docker targets remain available, but represent a historical build setup; inspect their revisions before use.

Scripts under `scripts/` own SL101 tooling. Generated builds, root filesystems, device state and evidence stay in ignored `tmp/`, `state/`, and `work/` directories. A small, attributed copy of the infrastructure transport helper remains under `src/android_infra/runner.py` so read-only preflight works without installing the Android infrastructure project. Existing evidence schema names retain their original identifiers for compatibility.

See [migration notes](docs/MIGRATION-20261003.md) for provenance and old-path compatibility. Historical logs contain their original paths and are not rewritten.

## Hardware qualification

Successful builds or EGL initialization are not proof of correct GPU rendering. Preserve the known working software-rendered recovery path; consult the latest dated hardware evidence before deployment. Flashing, boot persistence and suspend require exact device/artifact identity and their documented recovery gates. The old `README.org` flashing example is historical, not a verified partition recipe.
