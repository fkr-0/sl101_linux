# SL101 EGL resize/input harness review — 2026-10-03

Target: `root@192.168.23.106`, kernel `7.0.1-postmarketos-grate`, SD CID
`035344534c31323880ac79a543010300`. Driver unchanged:
`541e60b7ef948852be32f9d75c22f5f8aaa8e2e6e3548298aae2f4d0fc2c7815`.

## Demonstrated harness defects and corrections

The original 00:14 run logged the Resize action but received only zero-sized
terminal configure events. labwc selects the cursor view for keyboard Resize,
not the active keyboard view. Add WarpCursor to the active window before Resize.
The revised hardware run produces multiple nonzero terminal sizes.

The original helper sent PageUp/PageDown before releasing the resize grab.
Finish resize with a pointer-button release, click again to focus the client,
and require Wayland delivery of keycodes 104/109 and pointer button 272.
Open the exclusive Nura launcher only after those client input assertions.
The deferred panel launch must explicitly set XDG_RUNTIME_DIR, WAYLAND_DISPLAY,
and the qualification session DBus address.

Foot logs use `wl_surface#…`, while the old commit counter only accepted `@`.
The corrected counter accepts both. Against the archived failed-run log,
the old counter returns 0 and the corrected counter returns 34.

Evidence output is now unique per revision; existing runs are preserved and
an existing output directory is refused. Signal traps return nonzero after
rollback, rather than allowing cancellation to look like exit status zero.
Rollback also captures a kernel snapshot on failure/cancellation.

## Attempts

- r2: resize passed (789x458, 870x504, 1033x585), fullscreen close passed,
  early soak stable at 35632 KiB. Deliberately cancelled because client key
  delivery was missing; rollback passed. This is not an endurance pass.
- r3: resize, client key/pointer delivery and fullscreen close passed.
  Deferred Nura panel launch failed because the invoking shell did not supply
  XDG_RUNTIME_DIR. Aborted at soak start; rollback passed.
- r4: explicit panel runtime; full bounded qualification PASS, exit 0; rollback PASS.

Source and exact deployed harness snapshots:
`tmp/sl101-nura/gpu-promotion-20261002/stage-c/review-r4/`.
Target evidence: `/tmp/sl101-promotion-c-resize-r4/`.

Validation: shell syntax, shellcheck at warning severity, Python compilation,
archived-log counter regression and hardware input delivery.
No default renderer, boot, kernel or driver changes are part of this review.

## Final real-display result (08:43–08:55 CEST)

- Soak: 630 seconds, Grate/Tegra GLES2, compositor PID 14523.
- Scheduler: 3720 queued/run/completed; 3713 GR3D and 7 GR2D.
  Independent archived-trace recount confirms every GR3D queue came from labwc14523,
  with no lost-event markers.
- Fence signals: 11160; vblank events: 40325, delivered events: 1829.
- Normal terminal commits: 1742; Nura panel/menu commits: 17.
- Resize: three distinct nonzero configure sizes; PageUp/PageDown and
  a left-button press observed at the terminal protocol boundary.
- Compositor RSS: first/last/maximum all 34976 KiB (34.16 MiB).
- Kernel delta: only two expected uinput-device registrations; fault scan empty.
- Runtime PASS at 08:55:14; rollback PASS at 08:55:26; overall exit 0.
- Recovery: labwc20402 uses pixman, Nura panel20467, wayvnc20601;
  both desktop and WayVNC OpenRC services report started; private trace instance removed.
- Final evidence manifest: 14 hashes verified after local archival. Exact deployed
  script/helper hashes match archived source snapshots.

The original pre-cleanup manifest has one stale entry: labwc.stderr receives
normal shutdown lines during rollback. Its other eleven entries match.
Retain that original manifest and use evidence.final.sha256, captured after
rollback, for the final archived logs. The reusable harness now emits this
post-rollback manifest automatically (static-checked follow-up).

Tested harness SHA256: `028f123f90bb70f6f8393e7a214a9fb8f570675d4db1d4f812514ce573b21218`.
Helper SHA256: `55dd0c14f957c8264af7826901900a5b76cd37a96d9ee5ba426421968cfaa383`.

This establishes the bounded runtime/input/endurance gate. Physical visual
acceptance, cold-boot persistence, general application compatibility and
independent workflow approval for changing the default renderer remain separate.
