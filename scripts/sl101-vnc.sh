#!/bin/sh
set -eu
host=${1:-192.168.23.106}
port=${SL101_VNC_PORT:-5901}
socket=${XDG_RUNTIME_DIR:-/tmp}/sl101-vnc-$(id -u).sock
if ! ssh -S "$socket" -O check "root@$host" 2>/dev/null; then
    ssh -M -S "$socket" -fNT -o StrictHostKeyChecking=yes \
        -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
        -L "127.0.0.1:$port:127.0.0.1:5900" "root@$host"
fi
if command -v gvncviewer >/dev/null 2>&1; then
    exec gvncviewer "127.0.0.1:$((port - 5900))"
fi
printf 'Connect a VNC viewer to 127.0.0.1:%s\n' "$port"
