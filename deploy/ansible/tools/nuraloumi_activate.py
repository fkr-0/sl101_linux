#!/usr/bin/env python3
"""Atomic, reversible activation of one *already staged* NuraLoumi CI release.

Never builds binaries, installs APK keys, or touches the compositor/kernel.
Runs as root on the device via Ansible script module. --check is read-only.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ARM = "armv7-unknown-linux-musleabihf"
REQUIRED = {"nuraloumi-panel", "nuraloumi-menu", "nuraloumi-files",
            "nuraloumi-run", "nuraloumi-viewer",
            "nuraloumi-sway-workspace-switcher"}
EXISTING_REGULAR_ALLOWED = {"nuraloumi-sway-workspace-switcher"}
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
BIN_RE = re.compile(r"nuraloumi-[a-z0-9-]+\Z")


def ensure(yes, message):
    if not yes:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    temp = path.with_name(path.name + ".tmp")
    with temp.open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def atomic_link(path, dest):
    temp = path.with_name("." + path.name + ".nuraloumi-next")
    ensure(not os.path.lexists(temp), "preexisting temporary symlink: " + str(temp))
    os.symlink(str(dest), temp)
    os.replace(temp, path)


def safe_dir(path):
    ensure(path.is_dir() and not path.is_symlink(), "unsafe directory: " + str(path))


class Activation:
    def __init__(self, root, cli, sha, expected_old=None):
        ensure(SHA_RE.fullmatch(sha) is not None, "invalid full CI SHA")
        self.root, self.cli, self.sha = Path(root), Path(cli), sha
        self.release = self.root / "releases" / sha
        self.bin = self.release / "bin"
        self.current = self.root / "current"
        self.journal = self.release / "activation-rollback.json"
        self.backups = self.release / "activation-backup"
        self.names = []
        self.expected_old = Path(expected_old) if expected_old else None

    def inspect(self):
        safe_dir(self.root)
        safe_dir(self.root / "releases")
        safe_dir(self.release)
        safe_dir(self.bin)
        safe_dir(self.cli)
        ensure(self.current.is_symlink(), "no existing current symlink; refuse activation")
        old = Path(os.readlink(self.current))
        if not old.is_absolute():
            old = self.root / old
        ensure(old.is_dir() and (old.parent == self.root / "releases" or old == self.bin),
               "active pointer outside approved releases directory")
        manifest = self.release / "MANIFEST.txt"
        ready = self.release / "CI-READY"
        sums = self.release / "SHA256SUMS.bin"
        ensure(all(x.is_file() and not x.is_symlink() for x in (manifest, ready, sums)),
               "release provenance/CI-READY missing or symlinked")
        fields = dict(line.split("=", 1) for line in manifest.read_text().split("files:", 1)[0].splitlines()
                      if "=" in line)
        ensure(fields.get("git_commit") == self.sha and fields.get("git_dirty") == "false"
               and fields.get("target") == ARM, "release manifest identity mismatch")
        ensure("GIT_SHA=" + self.sha in ready.read_text() and
               "ABI=" + ARM in ready.read_text(), "CI readiness does not match release")
        names = fields.get("binaries", "").split(",")
        ensure(len(names) >= 24 and len(names) == len(set(names)) and
               REQUIRED.issubset(names) and all(BIN_RE.fullmatch(n) for n in names),
               "invalid or incomplete executable manifest")
        expected = {}
        for line in sums.read_text().splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  bin/(nuraloumi-[a-z0-9-]+)", line)
            ensure(match is not None and match[2] not in expected, "invalid SHA256SUMS.bin")
            expected[match[2]] = match[1]
        ensure(set(names) == set(expected), "checksum and binary list differ")
        ensure(set(p.name for p in self.bin.iterdir()) == set(names), "extra/unlisted binary in release")
        for name in names:
            path = self.bin / name
            ensure(path.is_file() and not path.is_symlink() and os.access(path, os.X_OK),
                   "missing/non-executable or symlinked CI tool: " + name)
            ensure(sha256(path) == expected[name], "CI tool checksum mismatch: " + name)
        self.names = names
        return old

    def preview(self):
        old = self.inspect()
        if old == self.bin:
            ensure(self.journal.is_file(), "active new release missing rollback receipt")
            self.verify_links()
            return {"result": "already-active", "old": str(old), "binaries": len(self.names)}
        if self.expected_old is not None:
            ensure(old == self.expected_old, "active pointer does not match reviewed old release")
        ensure(not self.journal.exists() and not self.backups.exists(),
               "partial/previous activation journal; rollback/review required")
        existing = {}
        for name in self.names:
            dest = self.cli / name
            if not os.path.lexists(dest):
                existing[name] = {"kind": "absent"}
            elif dest.is_symlink():
                link = os.readlink(dest)
                ensure(link == str(self.current / name),
                       "foreign symlink collision: " + str(dest))
                existing[name] = {"kind": "symlink", "target": link}
            elif dest.is_file() and name in EXISTING_REGULAR_ALLOWED:
                existing[name] = {"kind": "file"}
            else:
                raise ValueError("foreign executable collision: " + str(dest))
        return {"result": "ready", "old": str(old), "binaries": len(self.names),
                "existing": existing}

    def verify_links(self):
        ensure(self.current.is_symlink() and Path(os.readlink(self.current)) == self.bin,
               "current does not target exact verified CI bin")
        for name in self.names:
            dest = self.cli / name
            ensure(dest.is_symlink() and os.readlink(dest) == str(self.current / name),
                   "CLI tool not linked to active release: " + name)

    def activate(self):
        preview = self.preview()
        if preview["result"] == "already-active":
            print("NURALOUMI_ACTIVATION=ALREADY_ACTIVE " + self.sha)
            return
        ensure(os.geteuid() == 0, "only root can activate")
        journal = {"schema": "sl101-nuraloumi-activation-v1", "sha": self.sha,
                   "old": preview["old"], "existing": preview["existing"], "status": "prepared"}
        self.backups.mkdir(mode=0o700)
        for name, state in journal["existing"].items():
            if state["kind"] == "file":
                shutil.copy2(self.cli / name, self.backups / name, follow_symlinks=False)
                ensure(sha256(self.cli / name) == sha256(self.backups / name),
                       "could not safely back up existing CLI binary")
        write_json(self.journal, journal)
        try:
            atomic_link(self.current, self.bin)
            for name in self.names:
                atomic_link(self.cli / name, self.current / name)
            self.verify_links()
            journal["status"] = "active"
            write_json(self.journal, journal)
        except BaseException:
            self.rollback()
            raise
        print("NURALOUMI_ACTIVATION=ACTIVE sha=" + self.sha +
              " binaries=" + str(len(self.names)) + " old=" + preview["old"])

    def rollback(self):
        ensure(os.geteuid() == 0, "only root can roll back")
        ensure(self.journal.is_file() and not self.journal.is_symlink(),
               "missing trusted rollback receipt")
        record = json.loads(self.journal.read_text())
        ensure(record.get("sha") == self.sha and
               record.get("schema") == "sl101-nuraloumi-activation-v1",
               "rollback journal identity mismatch")
        old = Path(record["old"])
        ensure(old.parent == self.root / "releases" and old.is_dir(),
               "lost original release; cannot roll back")
        current_target = Path(os.readlink(self.current))
        ensure(current_target in (self.bin, old), "current changed by another actor")
        # Preflight EVERY restore operation before touching current. In
        # particular, a collision in one CLI path must not leave the
        # previous panel selected while other paths still target the CI build.
        for name, saved in record["existing"].items():
            dest = self.cli / name
            if saved["kind"] == "file":
                original = self.backups / name
                ensure(original.is_file() and not original.is_symlink(),
                       "missing original CLI backup: " + name)
            if dest.is_symlink():
                ensure(os.readlink(dest) == str(self.current / name),
                       "CLI entry changed by another actor: " + name)
            elif os.path.lexists(dest):
                ensure(saved["kind"] == "file",
                       "foreign CLI collision while rolling back: " + name)
        atomic_link(self.current, old)
        for name, saved in record["existing"].items():
            dest = self.cli / name
            # Only change our own symlink; never overwrite a third party.
            if dest.is_symlink():
                ensure(os.readlink(dest) == str(self.current / name),
                       "CLI entry changed by another actor: " + name)
            elif os.path.lexists(dest):
                ensure(saved["kind"] == "file", "CLI collision while rolling back")
                continue
            if saved["kind"] == "absent":
                if dest.is_symlink():
                    dest.unlink()
            elif saved["kind"] == "symlink":
                atomic_link(dest, saved["target"])
            else:
                original = self.backups / name
                ensure(original.is_file() and not original.is_symlink(),
                       "missing original CLI backup: " + name)
                staging = dest.with_name("." + name + ".nuraloumi-restore")
                ensure(not os.path.lexists(staging), "preexisting CLI restore path")
                shutil.copy2(original, staging)
                os.replace(staging, dest)
        record["status"] = "rolled-back"
        write_json(self.journal, record)
        print("NURALOUMI_ACTIVATION=ROLLED_BACK sha=" + self.sha + " restored=" + str(old))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sha", required=True)
    p.add_argument("--root", default="/opt/nuraloumi")
    p.add_argument("--cli", default="/usr/local/bin")
    p.add_argument("--expected-old")
    p.add_argument("action", choices=["check", "activate", "verify", "rollback"])
    a = p.parse_args()
    c = Activation(a.root, a.cli, a.sha, a.expected_old)
    if a.action == "check":
        print(json.dumps(c.preview(), sort_keys=True))
    elif a.action == "activate":
        c.activate()
    elif a.action == "verify":
        c.inspect()
        c.verify_links()
        print("NURALOUMI_ACTIVATION=VERIFIED " + a.sha)
    else:
        # Rollback must remain possible when a new CI binary, checksum
        # manifest or staging marker was corrupted after activation.
        # Its safety comes from the root-owned journal and exact old path.
        c.rollback()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print("NURALOUMI_ACTIVATION=FAILED " + str(e), file=sys.stderr)
        sys.exit(2)
