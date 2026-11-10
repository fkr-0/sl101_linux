# SL101: no kernel-release pins in the launchers, and a transparent render status (2026-11-10)

## Why

On the experimental kernel `7.0.1-postmarketos-grate-dmafix1` the browser could not be started
("Tablet identity mismatch"), and the desktop silently fell back to PIXMAN: `sl101-desktop` used
the Grate/EGL compositor only if `uname -r == 7.0.1-postmarketos-grate` and printed
`starting recovery pixman` to stderr only. Nothing told the operator how the screen was
actually rendered. The error text also blamed the "tablet identity" although only the kernel
release differed.

## What changed (repo and device)

* Kernel-release pins removed from `sl101-cog-control`, `sl101-cog-wpe-review`,
  `sl101-cog-kms-integrated`, `validate_grate()` in `sl101-renderer-switch` and the Grate
  decision in `sl101-desktop`. Hardware identity stays (hostname `sl101-nura` and the SD card
  CID: two identical tablets exist) with messages that say what differs
  (`hostname is 'x', expected 'sl101-nura'`). The library hash pins in `validate_grate` are
  provenance checks and stay.
* `sl101-desktop` decides by capability only (`sl101-renderer-verify`). A failed check falls
  back to PIXMAN loudly and records the reason. It writes `/run/sl101-render-status` (atomic,
  never fatal): compositor, backend, requested renderer, actual renderer, reason, kernel, prefix.
* `sl101-cog-control` prints and logs (`/var/log/sl101-cog-session.log`) a report on every start,
  and `sl101-cog-control status` shows it without starting anything:

```
sl101 rendering now:
  desktop : sway on DRM/KMS (wlroots drm backend), compositor renderer: PIXMAN (software, CPU)  <-- grate was requested but is NOT used: <reason>
  browser : Cog software mode: WebKit CPU rendering (Skia), buffers via shared memory, no EGL, GPU not used for page content
  kernel  : 7.0.1-postmarketos-grate-dmafix1 (informational, not checked)
```

  The desktop line uses the environment of the RUNNING compositor (`WLR_RENDERER`), not the
  configuration. The helper starts itself by its own path (`SELF`), so a copy works.
* Deliberately NOT changed: `sl101-kernel7-oneshot` (the kexec chain needs its recovery/target
  release), the library hash pins, the scripts' other checks.
* The panel (`NuraLoumi`, separate repository) can read `/run/sl101-render-status` for its renderer
  indicator instead of guessing from library paths.

## Deployment (done on 2026-11-10)

`scripts/sl101-no-release-pin-deploy-20261110.sh --plan | --apply | --rollback` (payload in
`work/sl101-render-transparency-20261110/payload`): verifies hostname + CID, requires the
expected installed hashes, writes backups `*.pre-norelpin-20261110` next to each file, installs
atomically. Rollback restores the backups. Verified on the tablet: all five files installed,
`sh -n`/`py_compile` ok, no release string left, `sl101-cog-control status` as root and as the
desktop user through `sudo`, `open https://de.wikipedia.org` through the production path started
Cog (software mode), the status writer under BusyBox ash with an unwritable path does not abort.
The desktop itself was not restarted: the running Sway still reports the fallback that the OLD
script caused; the real decision (Grate/EGL on this kernel) happens at the next desktop start.
Caution: the compositor with Grate/EGL on `dmafix1` has not been run yet; a hang there is
recovered by a power-cycle (stock kernel).

## Not done (proposal)

The browser entry points are still several names for overlapping jobs: `sl101-browse` (router:
Epiphany first, Badwolf, Cog fallback), `sl101-cog-url` (URL prompt, then `sudo
sl101-cog-control`), `sl101-cog-wpe`/`-root` (chain), `sl101-cog-wpe-review` and
`sl101-cog-control` (privileged helper). The panel opens URLs with `xdg-open`, whose default
handler is Epiphany (`sl101-epiphany.desktop`). Proposal: one user-facing `sl101-browse`
(`--prompt`, `--status`, `--software|--gpu`) that all keybinds, desktop files and the panel use,
with `sl101-cog-control` kept only as the privileged backend. That touches the Sway config,
desktop entries, sudoers and `DEPLOY.md`, so it is a separate change.
