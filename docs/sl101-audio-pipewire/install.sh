#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
grep -q 'WM8903' /proc/asound/cards || { echo "SL101 WM8903 card not found" >&2; exit 1; }

stamp=$(date +%Y%m%d-%H%M%S)
backup=/var/backups/sl101-audio-"$stamp"
mkdir -p "$backup"

backup_one() {
    path=$1
    if [ -e "$path" ]; then
        mkdir -p "$backup$(dirname "$path")"
        cp -p "$path" "$backup$path"
    fi
}

apk add --no-progress \
    pipewire pipewire-pulse wireplumber pulseaudio-utils \
    pipewire-spa-bluez bluez bluez-openrc

mkdir -p \
    /etc/pipewire/pipewire.conf.d \
    /etc/pipewire/pipewire-pulse.conf.d \
    /etc/wireplumber/wireplumber.conf.d

for path in \
    /etc/pipewire/pipewire.conf.d/10-sl101-clock.conf \
    /etc/pipewire/pipewire-pulse.conf.d/10-sl101-browser.conf \
    /etc/wireplumber/wireplumber.conf.d/51-sl101-wm8903.conf \
    /usr/local/bin/sl101-audio-session
do
    backup_one "$path"
done

install -m 0644 "$here/10-sl101-clock.conf" /etc/pipewire/pipewire.conf.d/10-sl101-clock.conf
install -m 0644 "$here/10-sl101-browser.conf" /etc/pipewire/pipewire-pulse.conf.d/10-sl101-browser.conf
install -m 0644 "$here/51-sl101-wm8903.conf" /etc/wireplumber/wireplumber.conf.d/51-sl101-wm8903.conf
install -m 0755 "$here/sl101-audio-session" /usr/local/bin/sl101-audio-session

rc-update add dbus default >/dev/null 2>&1 || true
rc-service dbus status >/dev/null 2>&1 || rc-service dbus start
rc-update add bluetooth default >/dev/null 2>&1 || true
rc-service bluetooth status >/dev/null 2>&1 || rc-service bluetooth start

/usr/local/bin/sl101-audio-session restart

pactl info | grep -q '^Default Sample Specification: .*44100Hz$'
pactl info | grep -q '^Default Sink: alsa_output.platform-sound.pro-output-0$'
! pactl list short sources | grep -q 'alsa_input.platform-sound.pro-input-0'
[ -S /run/sl101-audio/pulse-browser ]
[ "$(stat -c %a /run/sl101-audio/pulse-browser)" = 660 ]

printf 'SL101 PipeWire audio configured; backup=%s\n' "$backup"
pactl info | grep -E 'Server Name|Default Sample Specification|Default Sink|Default Source'
