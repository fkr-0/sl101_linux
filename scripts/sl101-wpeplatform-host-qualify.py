#!/usr/bin/env python3
"""Offline host qualification for the SL101 WPEPlatform-native harness."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work/sl101-wpe-armhf-build-qualification-20261003"
CONTROL = WORK / "wpe-audit/package-control.txt"
SHA256S = WORK / "wpe-audit/package-sha256.txt"
PACKAGES = WORK / "wpe-audit/packages"
AUDIT = WORK / "wpe-debug-audit/merged-elf-audit.json"
GRATE_AUDIT = WORK / "grate-build/grate-elf-audit.json"
WPE_LIBRARY = WORK / "wpe-audit/root/usr/lib/arm-linux-gnueabihf/libWPEWebKit-2.0.so.1.11.3"
CLOSURE_AUDIT = (
    ROOT / "work/sl101-wpe-runtime-closure-audit-20261004/full-root-audit.json"
)

EXPECTED_WPE_VERSION = "2.54.0-2"
EXPECTED_WPE_DEB = "libwpewebkit-2.0-1_2.54.0-2_armhf.deb"
EXPECTED_WPE_SHA256 = "0b3713cae5520fb44a6fcb099b0b23b8f2802bf3e3a57415fc36b9616bc84ffb"
SELECTED_PACKAGE_ALLOWED_FAILURES = {
    "usr/lib/arm-linux-gnueabihf/gstreamer1.0/gstreamer-1.0/gst-ptp-helper"
}
REQUIRED_RUNTIME_PATH_SUFFIXES = (
    "libWPEWebKit-2.0.so.1.11.3",
    "wpe-webkit-2.0/MiniBrowser",
    "wpe-webkit-2.0/WPEGPUProcess",
    "wpe-webkit-2.0/WPENetworkProcess",
    "wpe-webkit-2.0/WPEWebProcess",
)
REQUIRED_PACKAGE_DEPS = (
    "bubblewrap",
    "xdg-dbus-proxy",
    "libseccomp2",
    "libdrm2",
    "libgbm1",
    "libwayland-client0",
    "libwayland-egl1",
    "libwayland-server0",
)
REQUIRED_WPEPLATFORM_SYMBOLS = (
    "wpe_display_create_toplevel",
    "wpe_display_get_settings",
    "wpe_display_headless_new",
    "wpe_display_wayland_connect",
    "wpe_display_wayland_get_wl_display",
    "wpe_display_wayland_get_wl_shm",
    "wpe_display_wayland_new",
    "wpe_screen_drm_get_type",
    "wpe_view_wayland_get_wl_surface",
    "webkit_web_view_load_uri",
    "webkit_web_view_new",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def package_stanzas(text: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    current_file: str | None = None
    current: dict[str, str] = {}
    for line in text.splitlines():
        marker = re.fullmatch(r"===== (.+) =====", line)
        if marker:
            if current_file:
                result[current_file] = current
            current_file = marker.group(1)
            current = {}
            continue
        if current_file and ": " in line:
            key, value = line.split(": ", 1)
            current[key] = value
    if current_file:
        result[current_file] = current
    return result


def find_record(records: list[dict], suffix: str) -> dict | None:
    return next((r for r in records if r.get("path", "").endswith(suffix)), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-output", default="-", help="output path or - for stdout")
    args = ap.parse_args()

    required_files = (
        CONTROL,
        SHA256S,
        AUDIT,
        GRATE_AUDIT,
        WPE_LIBRARY,
        PACKAGES / EXPECTED_WPE_DEB,
    )
    missing = [str(p.relative_to(ROOT)) for p in required_files if not p.is_file()]
    if missing:
        payload = {
            "schema": "sl101.wpeplatform-native.host-qualification.v2",
            "pass": False,
            "missing": missing,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    controls = package_stanzas(CONTROL.read_text(encoding="utf-8"))
    wpe = controls.get(EXPECTED_WPE_DEB, {})
    depends = wpe.get("Depends", "")
    package_ok = (
        wpe.get("Package") == "libwpewebkit-2.0-1"
        and wpe.get("Version") == EXPECTED_WPE_VERSION
        and wpe.get("Architecture") == "armhf"
    )
    dependency_checks = {
        name: bool(
            re.search(
                rf"(?<![A-Za-z0-9.+-]){re.escape(name)}(?:\s|\(|,|$)",
                depends,
            )
        )
        for name in REQUIRED_PACKAGE_DEPS
    }

    listed_sha_ok = (
        f"{EXPECTED_WPE_SHA256}  {EXPECTED_WPE_DEB}"
        in SHA256S.read_text(encoding="utf-8")
    )
    actual_sha = sha256(PACKAGES / EXPECTED_WPE_DEB)
    package_sha_ok = listed_sha_ok and actual_sha == EXPECTED_WPE_SHA256

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    records = audit.get("records", [])
    failures = {f.get("path", "") for f in audit.get("failures", [])}
    unexpected_failures = sorted(failures - SELECTED_PACKAGE_ALLOWED_FAILURES)
    component_checks = {}
    for suffix in REQUIRED_RUNTIME_PATH_SUFFIXES:
        record = find_record(records, suffix)
        component_checks[suffix] = bool(record and not record.get("issues"))
    selected_package_cpu_ok = not unexpected_failures and all(component_checks.values())

    readelf = shutil.which("readelf")
    symbol_table = ""
    if readelf:
        proc = subprocess.run(
            [readelf, "-Ws", str(WPE_LIBRARY)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode == 0:
            symbol_table = proc.stdout
    symbol_checks = {
        symbol: symbol in symbol_table for symbol in REQUIRED_WPEPLATFORM_SYMBOLS
    }
    api_ok = bool(readelf) and all(symbol_checks.values())

    grate = json.loads(GRATE_AUDIT.read_text(encoding="utf-8"))
    grate_ok = grate.get("failure_count") == 0 and grate.get("elf_count", 0) > 0

    closure_ok = False
    closure_status = "unqualified"
    if CLOSURE_AUDIT.is_file():
        try:
            closure_payload = json.loads(CLOSURE_AUDIT.read_text(encoding="utf-8"))
            closure_ok = (
                closure_payload.get("schema") == "sl101.wpe.runtime-closure-audit.v1"
                and closure_payload.get("pass") is True
            )
            closure_status = "qualified" if closure_ok else "failed"
        except (OSError, json.JSONDecodeError):
            closure_status = "invalid-evidence"

    passed = (
        package_ok
        and package_sha_ok
        and all(dependency_checks.values())
        and selected_package_cpu_ok
        and closure_ok
        and api_ok
        and grate_ok
    )
    payload = {
        "schema": "sl101.wpeplatform-native.host-qualification.v2",
        "pass": passed,
        "engine": {
            "package": wpe.get("Package"),
            "version": wpe.get("Version"),
            "architecture": wpe.get("Architecture"),
            "deb": EXPECTED_WPE_DEB,
            "sha256": actual_sha,
            "sha256_matches": package_sha_ok,
        },
        "runtime_dependencies": dependency_checks,
        "wpeplatform_symbols": symbol_checks,
        "cpu_audit": {
            "scope": "selected-top-level-package-set-only",
            "elf_count": audit.get("elf_count"),
            "failure_count": audit.get("failure_count"),
            "allowed_failure_paths": sorted(SELECTED_PACKAGE_ALLOWED_FAILURES),
            "unexpected_failure_paths": unexpected_failures,
            "required_components_clean": component_checks,
            "selected_package_set_pass": selected_package_cpu_ok,
            "gst_ptp_helper_must_be_excluded": bool(
                failures & SELECTED_PACKAGE_ALLOWED_FAILURES
            ),
            "full_runtime_closure_qualified": closure_ok,
            "correction": (
                "The selected-package fetch omitted transitive dependencies such as "
                "libwebp7; a later SL101 page-load SIGILL in stock libwebp disproved "
                "using this audit as a full-runtime CPU-safety claim."
            ),
        },
        "runtime_closure": {
            "status": closure_status,
            "pass": closure_ok,
            "evidence": (
                str(CLOSURE_AUDIT.relative_to(ROOT))
                if CLOSURE_AUDIT.is_file()
                else None
            ),
            "required_tool": "scripts/sl101-wpe-runtime-closure-audit.py",
        },
        "grate_overlay_audit": {
            "elf_count": grate.get("elf_count"),
            "failure_count": grate.get("failure_count"),
            "pass": grate_ok,
        },
        "policy": {
            "network_access": False,
            "device_access": False,
            "sandbox_required": True,
            "renderer_default": "software",
            "gpu_opt_in": True,
            "webgl_gate": "separate",
            "skia_gate": "separate",
            "gbm_dmabuf_gate": "separate",
            "full_runtime_cpu_gate": "fail-closed-until-closure-audit",
        },
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.json_output == "-":
        print(rendered, end="")
    else:
        out = Path(args.json_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
