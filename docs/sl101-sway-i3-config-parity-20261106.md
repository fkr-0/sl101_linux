# SL101 Sway: workstation i3 keybinding parity (2026-11-06)

## Source, target, scope

- Reference: workstation `/home/user/.dotfiles/config/i3/config` SHA256 `c2a49cb2b0c359184184f58c7f1ce74226234335e552247100d7508506d1b369`.
- Source mirror: `docs/sl101-device-config/home/user/.config/sway/config`.
- Installed: `/home/user/.config/sway/config` on the exact `sl101-nura`, kernel `7.0.1-postmarketos-grate`, SD CID `035344534c31323880ac79a543010300`.
- Live compositor during deployment: `/usr/local/bin/sl101-sway` PID 7700, OpenRC `sl101-desktop`. No restart of the compositor was performed. Reload succeeded via Sway IPC.
- Installed config SHA256 `b0bdc987d592237174a04bfb5d4d824c09516fa2c052d79aefcd793f881217a6`; Sway IPC `get_config` matched the file byte for byte after reload.
- Renderer unchanged: `SL101_DESKTOP_RENDERER=grate`, `WLR_RENDERER=gles2`, `MESA_LOADER_DRIVER_OVERRIDE=grate`, `WLR_RENDERER_ALLOW_SOFTWARE=0`, and mapped private `libgallium-25.0.7.so`.
- Validation: `sway -C` returned 0 using isolated headless/Pixman checking environment; no second DRM compositor started. Actual physical key presses/layout were not automated.

## Workstation parity and deliberate changes

| Binding | Action |
| --- | --- |
| Super+Shift+Q | Close focused application window |
| Super+Shift+Space | Toggle focused window between floating and tiled |
| Super+G / Super+Ctrl+Space | Toggle focus between tiled and floating layer |
| Super+H/J/K/L or arrows | Focus left/down/up/right |
| Super+Shift+H/J/K/L or arrows | Move focused window in direction |
| Super+Tab / Super+Shift+Tab | Next/previous focus |
| Super+V / Super+Shift+V | Vertical/horizontal split |
| Super+S / Super+W / Super+E | Stacking/tabbed/toggle-split layout |
| Super+F | Fullscreen |
| Super+R | Resize mode (H/J/K/L or arrows; Esc/Enter to exit) |
| Super+Ctrl+H/J/K/L | Resize in direction |
| Super+1..0 | Workspace 1..10 (unless consumed by keyd) |
| Super+Shift+1..0 | Move container to numbered workspace (unless consumed by keyd) |
| Super+Ctrl+Left/Right | Previous/next workspace without conflicting with keyd |
| Super+Ctrl+Shift+Left/Right | Send container to previous/next workspace |
| Super+Minus / Super+Shift+Minus | Show scratchpad / move to scratchpad |
| Super+Shift+C / Super+Shift+R | Reload Sway configuration |
| Super+Return | Existing foot/tmux launcher |
| Super+D / Super+Space / Super+Period | NuraLoumi app launcher |
| Super+Shift+E | NuraLoumi Files, moved from Super+E to preserve i3 layout toggle |
| Alt+Tab / Super+O | NuraLoumi window switcher |
| Super+U / Super+B | Existing Cog URL / smart browser launcher |

**Default tiling:** removed the earlier blanket `for_window [app_id=".*"] floating enable` and matching X11 class rule. This changes *new* windows. Sway reload does not retile existing floating windows; toggle those manually with Super+Shift+Space. Transient dialogs and NuraLoumi launcher/menu keep targeted floating rules.

**Keyd / VT conflict:** the live `/etc/keyd/sl101.conf` rewrites Super+1..7 to Ctrl+Alt+F1..F7, even before Sway sees the keys. The existing Ctrl+Alt+F1..F7 `sl101-chvt` rescue bindings were intentionally preserved. To navigate workspaces on the physical slider keyboard without risking loss of VT escape, use Super+Ctrl+Left/Right, not the numeric bindings. External keyboards without the keyd rewriting may use numeric bindings.

**Not ported:** workstation-only X11 binaries and startup daemons (kitty, rofi, dunst, picom, polybar, copyq), lock/suspend/shutdown/reboot commands, workstation-specific Emacs helpers and graphics/design programs. This prevents accidental invocation of unavailable dependencies or unsafe SL101 sleep operations.

## Recovery / verification

The exact old file is backed up as `/var/lib/sl101-sway-i3-20261106/config.before` on the tablet. To revert only these Sway bindings without restarting the graphics device:

    ssh root@192.168.23.106 sh /var/lib/sl101-sway-i3-20261106/rollback.sh

The rollback acquires the standard qualification lock, restores the old file, and requests `swaymsg reload`.

To inspect the live config:

    ssh root@192.168.23.106 'cat /home/user/.config/sway/config'
    ssh root@192.168.23.106 'cat /etc/sl101-desktop-renderer.conf; cat /run/sl101-desktop.pid'

The older NuraLoumi renderer label `Unknown` is not evidence for Pixman. Its running-renderer probe historically allowed only a `labwc` process name; the running executable is `sl101-sway`. Source fix lives separately in `/home/user/code/nuraloumi/crates/nuraloumi-providers/src/renderer.rs` (not yet deployed).
