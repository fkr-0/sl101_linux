#!/usr/bin/env python3
"""Offline target ELF DT_NEEDED closure + ARMHF ISA audit.

This is a *release blocker*, not an on-device or dlopen/process-module proof.
It never executes ARM code, invokes the dynamic loader, deploys, or touches
devices. Run INSIDE the isolated ARMHF sysroot image with --root /.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

NEEDED_RE = re.compile(r"\(NEEDED\).*?\[([^\]]+)\]")
INTERP_RE = re.compile(r"\[Requesting program interpreter:\s*([^\]]+)\]")
SIMD_RE = re.compile(r"Tag_Advanced_SIMD_arch:\s*(\S+)")
FP_RE = re.compile(r"Tag_FP_arch:\s*([^\n]+)")
MACHINE_RE = re.compile(r"Machine:\s*ARM\b")
NEON_NAMES = re.compile(
    r"^(?:vld[1-4]|vst[1-4]|vtbl|vtbx|vdup|vext|vzip|vuzp|vtrn|"
    r"vrev(?:16|32|64)|vshl|vshr|vq\w+|vadd[wlhn]?\.i|"
    r"vsub[wlhn]?\.i|vmul\.i|vmla\.i|vmls\.i|vmax\.[uis]|"
    r"vmin\.[uis]|vpad\w*|vcnt|vceq\.i|vcge\.[uis]|vcgt\.[uis]|"
    r"vorr|vand|veor|vbic|vbsl|vorn|vsli|vsri|vmovl|vmovn)",
    re.IGNORECASE,
)
VFP4_NAMES = re.compile(r"^vf(?:ma|ms|nma|nms)\.(?:f32|f64)$", re.I)
NEON_INTEGER = re.compile(r"^v[a-z0-9]+\.(?:i|u)(?:8|16|32|64)$", re.I)
NEON_FLOAT_D = re.compile(r"^v(?:add|sub|mul|mla|mls|max|min|abs|neg|recpe|rsqrte|recps|rsqrts)\.f32$", re.I)
VECTOR_REGS = re.compile(r"\b(?:q(?:[0-9]|[12][0-9]|3[01])|d(?:1[6-9]|2[0-9]|3[01]))\b", re.I)
DISASM_RE = re.compile(r"^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2,8}\s+)+([a-z]\S*)\s*(.*)$", re.I)
LIB_DIRS = (
    "lib/arm-linux-gnueabihf", "usr/lib/arm-linux-gnueabihf",
    "usr/local/lib/arm-linux-gnueabihf", "lib", "usr/lib",
)


def run(*argv: str) -> str:
    res = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=30)
    if res.returncode:
        raise RuntimeError(f"{argv[0]} exited {res.returncode}: {res.stderr[:160]}")
    return res.stdout


def parse_needed(text: str) -> list[str]:
    return NEEDED_RE.findall(text)


def is_neon_attribute(attributes: str) -> bool:
    return bool(SIMD_RE.search(attributes))


def flagged_disassembly_line(line: str) -> str | None:
    m = DISASM_RE.match(line)
    if not m:
        return None
    mnemonic, operands = m.groups()
    # Vector NEON arithmetic can use d0..d15: high-register checks alone
    # miss instructions such as vadd.f32 d0,d2,d4 or vabal.u8 d0,d2,d4.
    first_operand = operands.strip().split(",", 1)[0].strip()
    low_d_vector = bool(NEON_FLOAT_D.match(mnemonic) and
                        re.match(r"^d\d+\b", first_operand, re.I))
    if (NEON_NAMES.match(mnemonic) or VFP4_NAMES.match(mnemonic) or
            NEON_INTEGER.match(mnemonic) or low_d_vector or
            VECTOR_REGS.search(operands)):
        return mnemonic + " " + operands[:110]
    return None


def full_disassembly(path: Path, objdump: str) -> str | None:
    """Stream disassembly: do not buffer WPE's multi-megabyte text section."""
    process = subprocess.Popen(
        [objdump, "-d", str(path)], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            problem = flagged_disassembly_line(line)
            if problem:
                process.kill()
                process.communicate()
                return problem
        _, err = process.communicate(timeout=120)
        if process.returncode:
            raise RuntimeError(f"objdump failed for {path}: {err[:180]}")
        return None
    except Exception:
        if process.poll() is None:
            process.kill()
            process.communicate()
        raise


def safe_target(root: Path, path: Path) -> Path | None:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            return None
        return resolved
    except (OSError, RuntimeError):
        return None


def resolve_library(root: Path, soname: str,
                    library_dirs: tuple[str, ...] = LIB_DIRS) -> Path | None:
    if not soname or "/" in soname or "\x00" in soname:
        return None
    for subdir in library_dirs:
        directory = Path(subdir)
        if directory.is_absolute():
            # Interpret absolute sysroot library dirs as paths within that root.
            directory = Path(str(directory).lstrip("/"))
        resolved = safe_target(root, root / directory / soname)
        if resolved is not None:
            return resolved
    return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def scan(root: Path, binary: Path, full: bool, objdump: str,
         library_dirs: tuple[str, ...] = LIB_DIRS,
         max_files: int = 2048) -> dict:
    root = root.resolve(strict=True)
    executable = safe_target(root, binary)
    if executable is None:
        raise ValueError("binary absent, outside requested sysroot, or symlink unsafe")
    tool = shutil.which("readelf")
    if not tool or (full and not shutil.which(objdump)):
        raise ValueError("required target ELF inspection tools are missing")

    queue = deque([executable])
    traversed: set[Path] = set()
    files: list[dict] = []
    missing: list[dict] = []
    forbidden: list[dict] = []
    while queue:
        path = queue.popleft()
        if path in traversed:
            continue
        if len(traversed) >= max_files:
            raise ValueError(f"ELF closure cap exceeded ({max_files})")
        traversed.add(path)
        relative = str(path.relative_to(root))
        item: dict = {"path": relative, "sha256": sha256(path)}
        header = run("readelf", "-hW", str(path))
        attributes = run("readelf", "-A", str(path))
        if not MACHINE_RE.search(header):
            forbidden.append({"path": relative, "reason": "non-ARM target"})
        if "hard-float ABI" not in header:
            forbidden.append({"path": relative, "reason": "non-hard-float ARM ABI"})
        fp = FP_RE.search(attributes)
        item["fp_attribute"] = fp.group(1).strip() if fp else None
        # A Tegra2 VFPv3-D16 root cannot be qualified solely from an
        # application compiled for D16 if linked libraries declare VFPv4,
        # ARMv8 FP or full VFPv3 (potential D16..D31 use).
        if fp and fp.group(1).strip() != "VFPv3-D16":
            forbidden.append({"path": relative, "reason":
                              "FP attribute outside VFPv3-D16: " + fp.group(1).strip()})
        simd = SIMD_RE.search(attributes)
        item["simd_attribute"] = simd.group(1) if simd else None
        if simd:
            forbidden.append({"path": relative, "reason": f"NEON attribute {simd.group(1)}"})
        # PT_INTERP is not a DT_NEEDED entry. It is still part of the
        # process's effective CPU/ABI runtime closure and must be present.
        interpreter_match = INTERP_RE.search(run("readelf", "-lW", str(path)))
        if interpreter_match:
            interpreter_name = interpreter_match.group(1)
            item["interpreter"] = interpreter_name
            if not interpreter_name.startswith("/"):
                missing.append({"required_by": relative, "interpreter": interpreter_name})
            else:
                target = safe_target(root, root / interpreter_name.lstrip("/"))
                if target:
                    queue.append(target)
                else:
                    missing.append({"required_by": relative, "interpreter": interpreter_name})
        if full:
            instruction = full_disassembly(path, objdump)
            item["disassembly"] = "fail" if instruction else "pass"
            if instruction:
                # objdump -d can incorrectly choose ARM for Thumb-2 text
                # when mapping symbols are stripped (observed libwebp at
                # .text+0). A suspicious mnemonic is a conservative blocker,
                # *not* proof that a real, reachable instruction was decoded.
                forbidden.append({"path": relative, "reason":
                                  f"potential forbidden ISA decode (ARM/Thumb mode unverified): {instruction}"})
        dependencies = parse_needed(run("readelf", "-dW", str(path)))
        item["needed"] = dependencies
        files.append(item)
        for soname in dependencies:
            match = resolve_library(root, soname, library_dirs)
            if match:
                queue.append(match)
            else:
                missing.append({"required_by": relative, "needed": soname})

    status = "blocked" if missing or forbidden else ("static-closure-audited" if full else "attributes-only")
    return {
        "schema": "sl101.nurabrowser.dt-needed-closure.v1",
        "status": status,
        "pass": not missing and not forbidden and full,
        "root": str(root),
        "binary": str(binary),
        "files_scanned": len(files),
        "missing": missing,
        "forbidden": forbidden,
        "files": files,
        "limitations": [
            "DT_NEEDED graph only; dlopen, GStreamer modules, WPEPlatform modules and child executables are NOT traversed",
            "ELF flags and disassembly are static evidence, not sandbox or runtime qualification",
            "Sysroot is rolling Debian unstable except the two exact WPE .deb archives",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--full-disassembly", action="store_true")
    parser.add_argument("--objdump", default="arm-linux-gnueabihf-objdump")
    parser.add_argument("--libdir", action="append", type=str,
                        help="Override target sysroot library search dirs")
    parser.add_argument("--max-files", type=int, default=2048)
    args = parser.parse_args()
    try:
        if args.max_files < 1:
            raise ValueError("--max-files must be positive")
        report = scan(args.root, args.binary, args.full_disassembly, args.objdump,
                      tuple(args.libdir) if args.libdir else LIB_DIRS,
                      args.max_files)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"pass": False, "status": "audit-error", "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
