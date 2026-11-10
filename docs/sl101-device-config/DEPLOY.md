# SL101 device configuration mirror

Tracked copies of device-side config files. Directory layout mirrors
the device filesystem root — deploy by copying to the matching path.

## Layout

```
docs/sl101-device-config/
├── etc/
│   ├── keyd/sl101.conf              → /etc/keyd/sl101.conf
│   └── local.d/sl101-alsa-restore.start → /etc/local.d/sl101-alsa-restore.start
├── home/user/.config/
│   ├── labwc/
│   │   ├── rc.xml                   → ~/.config/labwc/rc.xml
│   │   ├── autostart                → ~/.config/labwc/autostart
│   │   └── environment              → ~/.config/labwc/environment
│   ├── sway/config                  → ~/.config/sway/config
│   └── nuraloumi/config.toml        → ~/.config/nuraloumi/config.toml
└── usr/local/bin/
    ├── sl101-audio-session           → /usr/local/bin/sl101-audio-session
    ├── sl101-badwolf                 → /usr/local/bin/sl101-badwolf
    ├── sl101-browse                  → /usr/local/bin/sl101-browse
    ├── sl101-chvt                    → /usr/local/bin/sl101-chvt
    ├── sl101-cog-url                 → /usr/local/bin/sl101-cog-url
    ├── sl101-cog-wpe                 → /usr/local/bin/sl101-cog-wpe
    ├── sl101-desktop                 → /usr/local/bin/sl101-desktop
    ├── sl101-doom                    → /usr/local/bin/sl101-doom
    ├── sl101-firefox                 → /usr/local/bin/sl101-firefox
    ├── sl101-foot-launch             → /usr/local/bin/sl101-foot-launch
    ├── sl101-novnc                   → /usr/local/bin/sl101-novnc
    ├── sl101-restart-shell           → /usr/local/bin/sl101-restart-shell (labwc)
    ├── sl101-sway-panel              → /usr/local/bin/sl101-sway-panel (sway)
    ├── sl101-terminal-daemon         → /usr/local/bin/sl101-terminal-daemon
    ├── sl101-tmux-session            → /usr/local/bin/sl101-tmux-session
    └── sl101-zathura                 → /usr/local/bin/sl101-zathura
```

Not mirrored (large, deployment-specific, tracked elsewhere):
`sl101-cog-wpe-root`, `sl101-cog-wpe-review`, `sl101-cog-wpe-probe`,
`sl101-firefox-root`, `sl101-doom-root`.

## Reload commands

| Config | Reload |
|---|---|
| keyd | `keyd reload` |
| labwc rc.xml/environment | `kill -HUP $(pgrep -x labwc)` |
| labwc autostart | takes effect on next labwc start |
| sway config | `swaymsg reload` (or Super+Shift+R); `exec_always /usr/local/bin/sl101-sway-panel` restarts the panel without restarting the DRM compositor |
| XWayland | started by labwc autostart; needs labwc restart |
| ALSA restore | runs at boot via OpenRC local.d |

## Keyboard shortcuts (labwc + keyd)

| Shortcut | Action |
|---|---|
| Super+Return | New terminal (footclient + tmux) |
| Super+Shift+R | Under Sway, reload config and restart NuraLoumi panel via `exec_always` hook; under labwc, use its separate restart-shell binding |
| Super+Shift+Q | Close focused window |
| Super+U | Open URL in Cog |
| Super+B | Open browser (sl101-browse smart launcher) |
| Home+1..7 | VT switch (escape hatch via keyd meta layer) |

## keyd meta-layer: VT switching on the SL101 slider keyboard

The SL101 has no F-keys. The Fn key is firmware-level (Asus EC) and produces
plain number keycodes. Special key map:

| Physical key | Keycode |
|---|---|
| home-symbol / menu-symbol | `leftmeta` (Super) |
| magnifying-glass | `leftalt` |
| altgr | `rightalt` |
| backwards-symbol | `esc` |

The `[meta]` layer maps `leftmeta+1..7` → `Ctrl+Alt+F1..F7`:
- **In labwc:** keybindings catch `C-A-F1..F7` → `sl101-chvt N`
- **On text VT:** kernel console natively handles `Ctrl+Alt+Fn`

labwc runs on **VT1** (seatd assigns first available).

## Browser / PDF / VNC stack

XWayland starts in labwc autostart to enable GTK3/X11 apps (badwolf, zathura,
netsurf, gvncviewer). Required packages: `zathura zathura-pdf-mupdf novnc`.

| Launcher | Purpose |
|---|---|
| `sl101-browse` | Smart router: PDF→zathura, VNC→noVNC+Cog, web→badwolf/Cog |
| `sl101-badwolf` | WebKitGTK 2.48 browser (native Alpine, via XWayland) |
| `sl101-zathura` | PDF viewer (mupdf backend, via XWayland) |
| `sl101-novnc` | VNC client (noVNC websocket proxy + Cog) |
| `sl101-cog-wpe` | Cog/WPE (Debian chroot, no XWayland needed) |

Deploy with: `sh scripts/sl101-browser-deploy.sh --apply`

## ALSA (WM8903)

DAC Companding must be off (causes massive distortion). Saved state at
`/var/lib/alsa/asound.state`, restored at boot by `sl101-alsa-restore.start`.
