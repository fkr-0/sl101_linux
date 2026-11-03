#!/usr/bin/env python3
"""Safe staged installer. No writes unless --apply and explicit non-root target."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent

def load():
    return json.loads((HERE / "files-manifest.json").read_text())

def run():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["install", "rollback"])
    p.add_argument("--target-root", required=True, type=Path)
    p.add_argument("--backup", type=Path)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    root = a.target_root.resolve()
    if root == Path("/"):
        p.error("live root installation deliberately unsupported: lane 04 must review and adapt")
    if not root.is_dir():
        p.error("target-root must already exist")
    if a.apply and not (root / '.sl101-debian-staging').is_file():
        p.error('apply requires an explicitly marked disposable staging root')
    manifest = load()
    for entry in manifest:
        relpath = Path(entry['path'].lstrip('/'))
        if not entry['path'].startswith('/') or '..' in relpath.parts or not relpath.parts:
            p.error('invalid manifest path')
    backup = a.backup.resolve() if a.backup else None
    if a.apply and backup is None:
        p.error("--backup directory required for mutation")
    if backup and (backup == root or root in backup.parents or backup in root.parents):
        p.error("backup must be outside target root")
    if a.action == "rollback":
        if not backup or not (backup / "receipt.json").is_file():
            p.error("rollback requires an existing receipt")
        receipt = json.loads((backup / "receipt.json").read_text())
        actions = list(reversed(receipt["files"]))
    else:
        actions = manifest
    # Preflight every entry before the first target mutation, including journal paths.
    for entry in actions:
        relpath = Path(entry['path'].lstrip('/'))
        if not entry['path'].startswith('/') or '..' in relpath.parts or not relpath.parts:
            p.error('invalid journal or manifest path')
        rel = entry["path"].lstrip("/")
        target = root / rel
        if target.is_symlink() or any(q.is_symlink() for q in target.parents if q != root and root in q.parents):
            p.error("symlink in destination path: " + rel)
        if a.action == "install":
            src = HERE / rel
            if hashlib.sha256(src.read_bytes()).hexdigest() != entry["sha256"]:
                p.error("stale manifest hash: " + rel)
            if target.exists() and not target.is_file():
                p.error("non-regular target: " + rel)
    if a.apply and a.action == "install":
        if backup.exists():
            p.error("backup path already exists")
        backup.mkdir(parents=True)
        for entry in actions:
            rel = entry["path"].lstrip("/")
            target = root / rel
            entry["existed"] = target.is_file()
            if entry["existed"]:
                saved = backup / "old" / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
        # Durable rollback journal is written before modifying any target.
        (backup / "receipt.json").write_text(json.dumps({"files": actions, "root": str(root)}, indent=2) + "\n")
    if a.action == "rollback" and receipt.get("root") != str(root):
        p.error("rollback root does not match original installation")
    for entry in actions:
        rel = entry["path"].lstrip("/")
        target = root / rel
        if target.is_symlink() or any(q.is_symlink() for q in target.parents if q != root and root in q.parents):
            p.error("symlink in destination path: " + rel)
        print(a.action, target)
        if not a.apply:
            continue
        if a.action == "install":
            src = HERE / rel
            if hashlib.sha256(src.read_bytes()).hexdigest() != entry["sha256"]:
                p.error("stale manifest hash: " + rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
            target.chmod(int(entry["mode"], 8))
            # Ownership is intentionally not mutated for non-root test staging.
        else:
            if entry["existed"]:
                shutil.copy2(backup / "old" / rel, target)
            elif target.exists():
                target.unlink()

if __name__ == "__main__":
    run()
