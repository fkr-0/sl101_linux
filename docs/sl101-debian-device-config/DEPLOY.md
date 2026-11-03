# Native Debian SL101 configuration mirror

> STAGED configuration artifacts for lane 04. This mirror does **not** authorize deployment, package installation, renderer promotion or boot/session modification by lane 01.

## Scope and provenance

- Native Debian 13 (trixie) armhf / glibc, not Alpine, musl or a Debian chroot.
- Source counterpart: `../sl101-device-config/`, fully inventoried in `source-parity.json` (source SHA-256, source mode, disposition and rationale for each entry).
- Install payload: `files-manifest.json` (absolute target path, SHA-256, desired mode and intended ownership); no symlinks are expected in this currently inventoried source mirror.
- Supplemental package candidates: `packages.json`. Names are **not** evidence of package availability or architecture support.
- Do not run `rsync` over the entire source tree. Do not copy the old OpenRC local.d hook, root/chroot entrypoints, EGL preload or unqualified video/KMS scripts.

## Session and compositor

1. Establish a real local logind session through supported Debian PAM/systemd mechanisms. Debian manages `XDG_RUNTIME_DIR` and the per-user D-Bus socket; the desktop script validates ownership of that directory, does not create it, and never starts a private bus.
2. `sl101-desktop` starts labwc (or optional sway via `SL101_COMPOSITOR=sway`) with `WLR_RENDERER=pixman`. It clears stale EGL/GBM/loader/preload overrides. No acceleration request is accepted.
3. `etc/systemd/user/sl101-desktop.service` is an explicitly started user service with **no** Install section, not a boot/default target. Do not enable lingering or autologin merely to start it.
4. Preserve `XKB_DEFAULT_LAYOUT=de`; labwc and optional sway retain terminal, shell, navigation, browser and VT shortcuts. `keyd` still maps the slider meta-layer + digits 1–7 to Ctrl+Alt+Fn. Physical acceptance is required.
5. Switching VTs through `chvt` may require privilege. Lane 04 must establish a narrowly scoped, reviewed mechanism for the active local session or leave graphical VT shortcuts disabled; **no blanket passwordless sudo** is bundled. The native console Ctrl+Alt+Fn escape path remains independent.
6. The NuraLoumi binaries must be installed and qualified separately by the app build lane. `sl101-nuraloumi` uses only explicit native binary paths and exits with a clear error if unavailable. The panel autostart is optional.

## Audio and service ordering

Debian's `alsa-utils` state restore owns `/var/lib/alsa/asound.state`; this tree does not overwrite saved mixer state. If the WM8903 control exists and host qualification confirms card index and control semantics, lane 04 may enable `sl101-alsa-companding.service` **after** Debian `alsa-restore.service`. It changes DAC Companding only, not playback gain, capture controls, ADC Companding, microphone profiles, or defaults. Audio services otherwise use `systemctl --user` for PipeWire/WirePlumber, not private PID files or root-owned runtime sockets.

## Optional applications

- `sl101-browse`: local PDFs to native zathura; browser dispatch to Epiphany/Badwolf, then Cog if installed.
- `sl101-cog-wpe`: Cog Wayland platform, no chroot. Requires separately qualified Cog/WPE/EGL package compatibility.
- `sl101-novnc`: requires `SL101_NOVNC_URL` for an **existing approved proxy**; never starts an unauthenticated listener.
- Firefox, Doom and direct KMS video wrappers remain not applicable in the source parity manifest until independently qualified; they are not silently copied.
- Optional sway config preserves historical output mode/calibration but must be checked against actual live connector identity before activation.

## Candidate packages (not apt-verified)

Baseline: labwc, foot, tmux, keyd, alsa-utils, dbus-user-session, libpam-systemd. Optional: sway, zathura, zathura-pdf-mupdf, epiphany-browser, cog, badwolf, novnc, pipewire, wireplumber. Do not assume package names or armhf availability from an Alpine package list; record exact Debian source, version and archive signature during lane 04 preflight.

## Disposable host-side staging and rollback

From the repository root, a **local staging directory only**:

```sh
stage=$(mktemp -d)
mkdir -p "$stage/root"
: > "$stage/root/.sl101-debian-staging"
python3 docs/sl101-debian-device-config/install.py install --target-root "$stage/root"
python3 docs/sl101-debian-device-config/install.py install --target-root "$stage/root" --backup "$stage/backup" --apply
python3 docs/sl101-debian-device-config/install.py rollback --target-root "$stage/root" --backup "$stage/backup" --apply
```

Dry-run makes no writes. Apply requires the marker, an out-of-tree fresh backup path and a non-`/` target root. All files are hash-preflighted, conflicting directory/symlink destinations are rejected, previous regular files are backed up and a rollback journal is written before modifying the target. Staging copies apply mode but do not chown. This tool intentionally **cannot install into the live root**; lane 04 must provide a separate reviewed, identity-verified deployment transaction with private backups, exact user mapping, per-file provenance and rollback.

## Qualification levels

Host evidence: `python3 -m unittest discover -s docs/sl101-debian-device-config -p test_mirror.py`, `make test`, `make check`; the mirror tests validate every source hash, payload hashes, shell syntax, labwc XML/keymap, installer safety and staging unit loading.

Not asserted here: target package candidates, service activation/order at boot, local logind seat ownership, actual screen pixels, accelerated rendering, hardware keyboard/VT escape, audio playback/companding, browser/EGL or noVNC functionality. Lane 04 must test these individually after separate source/build review and remote read-only host identity/provenance verification. No deployable promotion follows from passing host tests.
