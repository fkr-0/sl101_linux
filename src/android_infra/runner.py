from __future__ import annotations

from dataclasses import asdict, dataclass
import shlex
import shutil
import subprocess
from typing import Sequence


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run(argv: Sequence[str], *, timeout: int = 30) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)


def adb_devices() -> list[dict[str, str]]:
    if not command_exists("adb"):
        return []
    result = run(["adb", "devices", "-l"])
    devices: list[dict[str, str]] = []
    for raw in result.stdout.splitlines()[1:]:
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        entry: dict[str, str] = {"serial": parts[0], "state": parts[1] if len(parts) > 1 else "unknown"}
        for token in parts[2:]:
            if ":" in token:
                key, value = token.split(":", 1)
                entry[key] = value
        devices.append(entry)
    return devices


def _parse_txt_record(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.split()
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key] = value
    return values


def parse_avahi_adb_services(output: str) -> list[dict[str, str]]:
    services: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in output.splitlines():
        if not raw.startswith("="):
            continue
        parts = raw.split(";", 9)
        if len(parts) < 9 or parts[4] != "_adb-tls-connect._tcp":
            continue
        _, interface, protocol, name, service, domain, host, address, port, *rest = parts
        endpoint = f"[{address}]:{port}" if ":" in address else f"{address}:{port}"
        if endpoint in seen:
            continue
        seen.add(endpoint)
        txt = _parse_txt_record(rest[0] if rest else "")
        services.append(
            {
                "name": name,
                "service": service,
                "domain": domain,
                "interface": interface,
                "protocol": protocol,
                "host": host,
                "address": address,
                "port": port,
                "endpoint": endpoint,
                "model": txt.get("name", ""),
                "api": txt.get("api", ""),
            }
        )
    return services


def parse_adb_mdns_services(output: str) -> list[dict[str, str]]:
    services: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("list of discovered"):
            continue
        parts = line.split()
        if len(parts) < 3 or parts[-2] != "_adb-tls-connect._tcp":
            continue
        name, service, endpoint = parts[-3:]
        if endpoint in seen or ":" not in endpoint:
            continue
        seen.add(endpoint)
        address, port = endpoint.rsplit(":", 1)
        services.append(
            {
                "name": name,
                "service": service,
                "domain": "local",
                "interface": "",
                "protocol": "",
                "host": "",
                "address": address.strip("[]"),
                "port": port,
                "endpoint": endpoint,
                "model": "",
                "api": "",
            }
        )
    return services


def wireless_adb_services() -> dict[str, object]:
    if command_exists("adb"):
        native = run(["adb", "mdns", "services"], timeout=5)
        services = parse_adb_mdns_services(native.stdout)
        if native.returncode == 0 and services:
            return {"backend": "adb-mdns", "services": services}

    if not command_exists("avahi-browse"):
        return {"backend": None, "services": []}

    try:
        completed = subprocess.run(
            ["avahi-browse", "-rtp", "_adb-tls-connect._tcp"],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
        stdout = completed.stdout
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
    return {"backend": "avahi-browse", "services": parse_avahi_adb_services(stdout)}


def connect_wireless_adb(services: Sequence[dict[str, str]]) -> list[dict[str, object]]:
    if not command_exists("adb"):
        return []
    attempts: list[dict[str, object]] = []
    seen: set[str] = set()
    for service in services:
        endpoint = service.get("endpoint", "")
        if not endpoint or endpoint in seen:
            continue
        seen.add(endpoint)
        result = run(["adb", "connect", endpoint], timeout=10)
        message = (result.stdout + "\n" + result.stderr).strip().casefold()
        connected = result.returncode == 0 and (
            message.startswith("connected to ") or message.startswith("already connected to ")
        )
        attempts.append(
            {
                "endpoint": endpoint,
                "returncode": result.returncode,
                "connected": connected,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        )
    return attempts


def fastboot_devices() -> list[dict[str, str]]:
    if not command_exists("fastboot"):
        return []
    result = run(["fastboot", "devices", "-l"])
    devices: list[dict[str, str]] = []
    for raw in result.stdout.splitlines():
        parts = raw.strip().split()
        if not parts:
            continue
        devices.append({"serial": parts[0], "details": " ".join(parts[1:])})
    return devices


def choose_adb_serial(serial: str | None = None) -> str:
    if serial:
        return serial
    candidates = [item["serial"] for item in adb_devices() if item.get("state") == "device"]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError("no authorized adb device detected")
    raise RuntimeError("multiple adb devices detected; pass --serial")


def inspect_adb(serial: str | None = None, *, include_packages: bool = False) -> dict[str, object]:
    if not command_exists("adb"):
        raise RuntimeError("adb is not installed or not on PATH")
    serial = choose_adb_serial(serial)
    props = {
        "manufacturer": "ro.product.manufacturer",
        "model": "ro.product.model",
        "device": "ro.product.device",
        "product": "ro.product.name",
        "android_release": "ro.build.version.release",
        "sdk": "ro.build.version.sdk",
        "build_fingerprint": "ro.build.fingerprint",
        "security_patch": "ro.build.version.security_patch",
        "bootloader": "ro.bootloader",
        "verified_boot_state": "ro.boot.verifiedbootstate",
        "slot_suffix": "ro.boot.slot_suffix",
    }
    report: dict[str, object] = {"transport": "adb", "serial": serial, "properties": {}}
    prop_out: dict[str, str] = {}
    for label, prop in props.items():
        result = run(["adb", "-s", serial, "shell", "getprop", prop])
        prop_out[label] = result.stdout.strip()
    report["properties"] = prop_out
    report["battery"] = run(["adb", "-s", serial, "shell", "dumpsys", "battery"]).stdout.strip()
    report["storage"] = run(["adb", "-s", serial, "shell", "df", "-h", "/data"]).stdout.strip()
    if include_packages:
        packages = run(["adb", "-s", serial, "shell", "pm", "list", "packages", "-3"]).stdout.splitlines()
        report["third_party_packages"] = [line.removeprefix("package:") for line in packages if line.strip()]
    return report


def choose_fastboot_serial(serial: str | None = None) -> str:
    if serial:
        return serial
    candidates = [item["serial"] for item in fastboot_devices()]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError("no fastboot device detected")
    raise RuntimeError("multiple fastboot devices detected; pass --serial")


def inspect_fastboot(serial: str | None = None) -> dict[str, object]:
    if not command_exists("fastboot"):
        raise RuntimeError("fastboot is not installed or not on PATH")
    serial = choose_fastboot_serial(serial)
    variables: dict[str, str] = {}
    for name in ("product", "version-bootloader", "current-slot", "unlocked", "secure"):
        result = run(["fastboot", "-s", serial, "getvar", name])
        text = (result.stdout + "\n" + result.stderr).strip()
        variables[name] = text
    return {"transport": "fastboot", "serial": serial, "variables": variables}
