# Persist each interactive command, including across concurrent SSH/foot shells.
HISTFILE=${XDG_STATE_HOME:-$HOME/.local/state}/zsh/history
HISTSIZE=20000
SAVEHIST=20000
(umask 077; mkdir -p -- "${HISTFILE:h}"; touch -- "$HISTFILE")
chmod 600 -- "$HISTFILE"
setopt EXTENDED_HISTORY SHARE_HISTORY HIST_FCNTL_LOCK
setopt HIST_IGNORE_DUPS HIST_SAVE_NO_DUPS HIST_IGNORE_SPACE
# SHARE_HISTORY provides incremental append and imports other sessions' history.
# Do not combine it with INC_APPEND_HISTORY or INC_APPEND_HISTORY_TIME.
