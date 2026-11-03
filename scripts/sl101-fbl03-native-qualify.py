#!/usr/bin/env python3
"""Strict host-native DP2 lowering qualification; never a GPU/pixel claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/sl101-fbl03-native"
MANIFEST = FIXTURE / "manifest.json"
TARGET = "src/gallium/drivers/grate/libgrate.a.p/fp_tgsi.c.o"


def require_hash(path, digest):
    if not path.is_file():
        raise RuntimeError(f"missing required input: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise RuntimeError(f"SHA-256 mismatch: {path}: {actual} != {digest}")


def qualify(build):
    m = json.loads(MANIFEST.read_text())
    for relative, digest in m["inputs"].items():
        require_hash(ROOT / relative, digest)
    if not (build / "build.ninja").is_file():
        raise RuntimeError(f"missing configured Mesa build.ninja: {build}; see fixture README")
    with tempfile.TemporaryDirectory(prefix="sl101-fbl03-native-") as td:
        stage = Path(td)
        target = stage / "src/gallium/drivers/grate/fp/tgsi.c"
        target.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURE / "rebased-base.c", target)
        for patch in m["patch_order"]:
            cmd = ["git", "apply", "--check", str(ROOT / patch)]
            subprocess.run(cmd, cwd=stage, check=True)
            subprocess.run(["git", "apply", str(ROOT / patch)], cwd=stage, check=True)
        require_hash(target, m["patched_sha256"])
        fp = stage / "grate/fp"
        fp.mkdir(parents=True)
        shutil.copyfile(target, fp / "tgsi.c")
        shutil.copyfile(FIXTURE / "grate_compiler.h", stage / "grate/grate_compiler.h")
        shutil.copyfile(FIXTURE / "fpir.h", fp / "fpir.h")
        shutil.copyfile(FIXTURE / "test_dp2.c", fp / "test_dp2.c")
        result = subprocess.run(["ninja", "-C", str(build), "-t", "commands", TARGET],
                                capture_output=True, text=True, check=True)
        lines = result.stdout.strip().splitlines()
        if not lines:
            raise RuntimeError("ninja emitted no fp/tgsi.c compile command")
        args = shlex.split(lines[-1])
        args[0] = "gcc"  # host compiler, not ARM cross compiler
        args = [v for v in args if not v.startswith(("-march=", "-mfpu=", "-mfloat-abi="))
                and v != "-DUSE_ARM_ASM"]
        for flag in ("-MD", "-MQ", "-MF", "-o", "-c"):
            if flag in args:
                i = args.index(flag)
                del args[i:i + (1 if flag in ("-MD", "-c") else 2)]
        args = [v for v in args if v != "../src/gallium/drivers/grate/fp/tgsi.c"]
        binary = stage / "native-lowering"
        args.extend(["-Wl,--gc-sections", "-o", str(binary), str(fp / "test_dp2.c")])
        subprocess.run(args, cwd=build, check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesa-build", type=Path,
                        default=Path(os.environ.get("SL101_FBL03_MESA_BUILD",
                                                 ROOT / "build/mesa-grate-clean/mesa-25.0.7/builddir")),
                        help="existing configured Mesa Grate build directory; required for includes")
    a = parser.parse_args()
    try:
        qualify(a.mesa_build.resolve())
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"FAIL: FBL03 native qualification: {exc}", file=sys.stderr)
        sys.exit(1)
