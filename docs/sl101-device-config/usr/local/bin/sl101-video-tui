#!/usr/bin/env python3
"""TUI for launching VDE hardware-decoded video on the SL101.

Runs inside tmux on the device. Lists mp4 files, lets you pick one,
transfers from host if needed, and kicks off KMS playback detached
so it survives compositor stop/restart.

Usage:
  On the SL101 (in tmux):  python3 sl101-video-tui.py [MEDIA_DIR]
  From the host:           ssh root@192.168.23.106 python3 /path/sl101-video-tui.py

MEDIA_DIR defaults to /home/user.
"""
import curses
import glob
import os
import subprocess
import sys

MEDIA_DIR = sys.argv[1] if len(sys.argv) > 1 else "/home/user"
PLAYER = "/usr/local/bin/sl101-video-kms-play"
EXTENSIONS = (".mp4", ".mkv", ".avi", ".webm")


def find_media(directory):
    files = []
    for f in sorted(os.listdir(directory)):
        if any(f.lower().endswith(ext) for ext in EXTENSIONS):
            full = os.path.join(directory, f)
            if os.path.isfile(full):
                size_mb = os.path.getsize(full) / (1024 * 1024)
                files.append((f, full, size_mb))
    return files


def play_file(path):
    """Launch detached KMS playback. Returns immediately."""
    subprocess.Popen(
        ["sh", PLAYER, path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def probe_file(path):
    """Get codec info via ffprobe."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_name,profile,width,height,avg_frame_rate",
                "-of", "compact=p=0:nk=1",
                path,
            ],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip().split("\n") if r.returncode == 0 else ["probe failed"]
    except Exception as e:
        return [str(e)]


def draw_menu(stdscr, files, selected, status, probe_info):
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    title = "SL101 VDE Video Player"
    stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)
    stdscr.addstr(1, 0, f"Media: {MEDIA_DIR}", curses.A_DIM)
    stdscr.addstr(2, 0, "─" * min(w - 1, 60))

    if not files:
        stdscr.addstr(4, 2, "No media files found.", curses.A_DIM)
        stdscr.addstr(5, 2, f"Place .mp4 files in {MEDIA_DIR}")
    else:
        max_visible = h - 8
        start = max(0, selected - max_visible + 1)
        for i, (name, _, size_mb) in enumerate(files[start:start + max_visible]):
            idx = start + i
            row = 3 + i
            if row >= h - 4:
                break
            label = f"  {name}  ({size_mb:.0f} MB)"
            if len(label) >= w:
                label = label[:w - 2]
            attr = curses.A_REVERSE if idx == selected else curses.A_NORMAL
            stdscr.addstr(row, 0, label, attr)

    # Probe info
    if probe_info:
        info_row = h - 3
        for i, line in enumerate(probe_info[:2]):
            if info_row + i < h - 1 and len(line) < w:
                stdscr.addstr(info_row + i, 2, line, curses.A_DIM)

    # Status bar
    bar = f" {status} " if status else " Enter=Play  p=Probe  q=Quit  r=Refresh "
    if len(bar) >= w:
        bar = bar[:w - 1]
    stdscr.addstr(h - 1, 0, bar, curses.A_BOLD)

    stdscr.refresh()


def main(stdscr):
    curses.curs_set(0)
    stdscr.timeout(-1)

    files = find_media(MEDIA_DIR)
    selected = 0
    status = ""
    probe_info = []
    dirty = True

    while True:
        if dirty:
            draw_menu(stdscr, files, selected, status, probe_info)
            dirty = False
        key = stdscr.getch()
        if key == -1:
            continue

        dirty = True
        if key == ord("q") or key == 27:
            break
        elif key == curses.KEY_UP or key == ord("k"):
            if selected > 0:
                selected -= 1
                probe_info = []
        elif key == curses.KEY_DOWN or key == ord("j"):
            if selected < len(files) - 1:
                selected += 1
                probe_info = []
        elif key == ord("r"):
            files = find_media(MEDIA_DIR)
            selected = min(selected, max(0, len(files) - 1))
            status = f"Refreshed: {len(files)} files"
            probe_info = []
        elif key == ord("p") and files:
            _, path, _ = files[selected]
            status = "Probing..."
            draw_menu(stdscr, files, selected, status, probe_info)
            probe_info = probe_file(path)
            status = ""
        elif (key == ord("\n") or key == curses.KEY_ENTER) and files:
            name, path, _ = files[selected]
            if not os.path.exists(PLAYER):
                status = f"Player not found: {PLAYER}"
                continue
            status = f"Starting: {name}"
            draw_menu(stdscr, files, selected, status, probe_info)
            play_file(path)
            status = f"Playing: {name} (detached)"
        elif key == curses.KEY_RESIZE:
            pass
        else:
            dirty = False


if __name__ == "__main__":
    curses.wrapper(main)
