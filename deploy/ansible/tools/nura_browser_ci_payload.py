#!/usr/bin/env python3
"""Import ONLY one successful GitHub Actions ARMHF NuraBrowser release.

No local compilation, download URL override, or arbitrary tar allowed.
Produces controller-local, Git-ignored data for the guarded Ansible stage.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SOURCE_REPO = "fkr-0/sl101_linux"
WORKFLOW = ".github/workflows/nura-browser-armhf.yml"
VERIFY_SCRIPT = Path(__file__).resolve().parents[3] / "nura-browser/scripts/verify-ci-release.py"
SHA = re.compile(r"[a-f0-9]{40}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
RUN_ID = re.compile(r"[1-9][0-9]*\Z")


def run_process(args: list[str], *, timeout: int = 60) -> str:
    result = subprocess.run(
        args, check=True, text=True, capture_output=True,
        timeout=timeout, env={**os.environ, "GH_PROMPT_DISABLED": "1"}
    )
    return result.stdout


def fetch_verified_run(sha: str, run_id: str) -> dict:
    response = run_process([
        "gh", "api", f"repos/{SOURCE_REPO}/actions/runs/{run_id}"
    ])
    data = json.loads(response)
    expected = {
        "id": int(run_id),
        "head_sha": sha,
        "conclusion": "success",
        "status": "completed",
        "path": WORKFLOW,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            raise ValueError(f"GitHub run {key} mismatch: {data.get(key)!r}")
    if data.get("event") not in ("push", "workflow_dispatch"):
        raise ValueError("unsupported GitHub workflow event")
    if not (data.get("head_branch") == "main" or
            data.get("head_branch", "").startswith("nurabrowser-ci-")):
        raise ValueError("unapproved GitHub source branch")
    repo = data.get("repository") or {}
    if repo.get("full_name") != SOURCE_REPO:
        raise ValueError("workflow did not run in the expected repository")
    return {
        "schema": "sl101.nurabrowser.github-run-attestation.v1",
        "source_repo": SOURCE_REPO,
        "sha": sha,
        "run_id": run_id,
        "event": data["event"],
        "branch": data["head_branch"],
        "workflow": WORKFLOW,
        "conclusion": "success",
        "attempt": data.get("run_attempt", 1),
        "url": data.get("html_url"),
    }


def verify_local(payload: Path, sha: str, run_id: str, tar_sha: str) -> dict:
    response = run_process([
        sys.executable, str(VERIFY_SCRIPT),
        "--artifact-dir", str(payload),
        "--sha", sha,
        "--run-id", run_id,
        "--tar-sha256", tar_sha,
    ], timeout=35)
    return json.loads(response)


def prepare(sha: str, run_id: str, tar_sha: str, output: Path) -> dict:
    github_receipt = fetch_verified_run(sha, run_id)
    final = output / sha
    if final.exists():
        if final.is_symlink():
            raise ValueError("existing payload destination is a symlink")
        receipt = verify_local(final, sha, run_id, tar_sha)
        saved = json.loads((final / "CI-GITHUB-RUN.json").read_text())
        if saved != github_receipt:
            raise ValueError("existing GitHub run receipt disagrees")
        return receipt

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".nura-ci-{sha[:12]}-", dir=output) as temp:
        stage = Path(temp)
        artifact_name = f"nurabrowser-armhf-{run_id}-{sha}"
        run_process([
            "gh", "run", "download", run_id,
            "--repo", SOURCE_REPO,
            "--name", artifact_name,
            "--dir", str(stage),
        ], timeout=260)
        receipt = verify_local(stage, sha, run_id, tar_sha)
        (stage / "CI-GITHUB-RUN.json").write_text(
            json.dumps(github_receipt, indent=2, sort_keys=True) + "\n"
        )
        (stage / "CI-VERIFIED.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )
        # No symlink or extra file may be added after the verified import.
        os.chmod(stage, 0o700)
        stage.rename(final)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "verify"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tar-sha256", required=True)
    parser.add_argument("--out-root", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/nura-browser")
    args = parser.parse_args()
    if not SHA.fullmatch(args.sha) or not RUN_ID.fullmatch(args.run_id):
        parser.error("expected exact 40-digit lowercase source SHA and GitHub run ID")
    if not HASH.fullmatch(args.tar_sha256):
        parser.error("expected exact approved SHA256")
    try:
        if args.operation == "prepare":
            receipt = prepare(args.sha, args.run_id, args.tar_sha256, args.out_root)
        else:
            final = args.out_root / args.sha
            receipt = verify_local(final, args.sha, args.run_id, args.tar_sha256)
            saved = json.loads((final / "CI-GITHUB-RUN.json").read_text())
            if saved["sha"] != args.sha or saved["run_id"] != args.run_id or saved["workflow"] != WORKFLOW:
                raise ValueError("saved GitHub attestation mismatch")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, KeyError, json.JSONDecodeError) as exc:
        print(f"REFUSED CI-only import: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
