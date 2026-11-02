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
│   └── nuraloumi/config.toml        → ~/.config/nuraloumi/config.toml
└── usr/local/bin/
    ├── sl101-audio-session           → /usr/local/bin/sl101-audio-session
    ├── sl101-chvt                    → /usr/local/bin/sl101-chvt
    ├── sl101-cog-url                 → /usr/local/bin/sl101-cog-url
    ├── sl101-cog-wpe                 → /usr/local/bin/sl101-cog-wpe
    ├── sl101-desktop                 → /usr/local/bin/sl101-desktop
    ├── sl101-doom                    → /usr/local/bin/sl101-doom
    ├── sl101-firefox                 → /usr/local/bin/sl101-firefox
    ├── sl101-foot-launch             → /usr/local/bin/sl101-foot-launch
    ├── sl101-restart-shell           → /usr/local/bin/sl101-restart-shell
    ├── sl101-terminal-daemon         → /usr/local/bin/sl101-terminal-daemon
    └── sl101-tmux-session            → /usr/local/bin/sl101-tmux-session
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
| ALSA restore | runs at boot via OpenRC local.d |

## Keyboard shortcuts (labwc + keyd)

| Shortcut | Action |
|---|---|
| Super+Return | New terminal (footclient + tmux) |
| Super+Shift+R | Restart nuraloumi-panel + reconfigure labwc |
| Super+Shift+Q | Close focused window |
| Super+U | Open URL in Cog |
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

## ALSA (WM8903)

DAC Companding must be off (causes massive distortion). Saved state at
`/var/lib/alsa/asound.state`, restored at boot by `sl101-alsa-restore.start`.
