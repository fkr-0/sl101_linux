# SL101 temporary files and shell history

On October 3, the 1 GiB tablet's existing OpenRC `tmpfs` boot service was
configured with `tmpfs_size=128m` in `/etc/conf.d/tmpfs`. It mounts `/tmp` with
mode 1777, nosuid and nodev before bootmisc. The limit is a ceiling, not reserved
memory. This is staged for the next boot; no live mount or reboot was performed.
`wipe_tmp` remains NO. Desktop restarts must not clear shared temporary files.

Existing disk-backed `/tmp` files remain underneath the future mount. They are
not deleted, and this change does not reclaim their disk space. Keep large
build inputs in `/var/tmp`, installed runtimes in `/opt`, and durable evidence
in `/var/lib` or the host archive. The attempted full live `/tmp` archive was
cancelled when switching to tmpfs; `tmp-partial-not-a-backup.tar` is incomplete
and must not be used for recovery. Config backups are in
`/var/lib/sl101-system-hygiene/20261003/`.

Installed `90-sl101-history.zsh` under `/etc/zsh/zshrc.d/`. New interactive
shells save up to 20000 entries under `$XDG_STATE_HOME/zsh/history`, defaulting
to `~/.local/state/zsh/history`, mode 600. SHARE_HISTORY appends commands as
entered and imports concurrent sessions; a separate interactive shell verified
the probe command persisted. Existing shells must source the new file or reopen.
Commands prefixed with a space are excluded from history.

The visible compositor listens on `/run/user/0/wayland-0`. Labwc also owns the
X0 socket for lazy Xwayland compatibility, which does not make it an X11 desktop.
X1's lock PID was absent and no listener owned its socket: stale test debris.

After the next system boot, verify `mountinfo -q -f tmpfs /tmp`, the 128 MiB
capacity in `df -h /tmp`, and fresh history in a new interactive zsh. A boot test
has not yet been performed. Revert by restoring `tmpfs.before` before a reboot;
do not unmount `/tmp` while applications use it.
