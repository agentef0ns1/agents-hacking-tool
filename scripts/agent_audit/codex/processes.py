"""Detección de procesos Codex y extracción de /proc/pid."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

CODEX_MATCHERS = (
    "@openai/codex",
    "ollama launch codex",
    "/bin/codex",
    "node_modules/.bin/codex",
    "node_modules/@openai/codex",
)

AUDIT_TOOL_MARKERS = ("agent-audit-cli", "audit-agent-surface")


@dataclass
class ProcSnapshot:
    pid: int
    cmdline: str
    name: str | None = None
    state: str | None = None
    ppid: int | None = None
    uid: str | None = None
    gid: str | None = None
    vm_rss_kb: int | None = None
    cwd: str | None = None
    environ: dict[str, str] = field(default_factory=dict)
    open_fds: int | None = None
    matched_on: str | None = None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _read_cmdline(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def _parse_status(path: Path) -> dict[str, str]:
    text = _read_text(path)
    if not text:
        return {}
    data: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _parse_environ(path: Path) -> dict[str, str]:
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    env: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, _, value = item.partition(b"=")
        try:
            env[key.decode("utf-8", errors="replace")] = value.decode(
                "utf-8", errors="replace"
            )
        except UnicodeDecodeError:
            continue
    return env


def _count_fds(pid: int) -> int | None:
    fd_dir = Path(f"/proc/{pid}/fd")
    try:
        return len(list(fd_dir.iterdir()))
    except OSError:
        return None


def _matches_codex(cmdline: str) -> str | None:
    lower = cmdline.lower()
    if any(marker in lower for marker in AUDIT_TOOL_MARKERS):
        return None
    for needle in CODEX_MATCHERS:
        if needle.lower() in lower:
            return needle
    for token in cmdline.split():
        base = Path(token).name.lower()
        if base in {"codex", "codex.js"} or base.startswith("codex-"):
            return token
    return None


def scan_codex_processes() -> list[ProcSnapshot]:
    results: list[ProcSnapshot] = []
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return results

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline = _read_cmdline(entry / "cmdline")
        if not cmdline:
            continue
        matched = _matches_codex(cmdline)
        if not matched:
            continue

        status = _parse_status(entry / "status")
        cwd = None
        try:
            cwd = os.readlink(entry / "cwd")
        except OSError:
            cwd = None

        vm_rss = None
        if status.get("VmRSS"):
            try:
                vm_rss = int(status["VmRSS"].split()[0])
            except (ValueError, IndexError):
                vm_rss = None

        relevant_env = {}
        full_env = _parse_environ(entry / "environ")
        for key in (
            "HOME",
            "USER",
            "PWD",
            "CODEX_HOME",
            "OLLAMA_HOST",
            "PATH",
            "SANDBOX",
        ):
            if key in full_env:
                relevant_env[key] = full_env[key]
        for key, value in full_env.items():
            if "codex" in key.lower() or "ollama" in key.lower():
                relevant_env[key] = value

        results.append(
            ProcSnapshot(
                pid=pid,
                cmdline=cmdline,
                name=status.get("Name"),
                state=status.get("State"),
                ppid=int(status["PPid"]) if status.get("PPid", "").isdigit() else None,
                uid=status.get("Uid"),
                gid=status.get("Gid"),
                vm_rss_kb=vm_rss,
                cwd=cwd,
                environ=relevant_env,
                open_fds=_count_fds(pid),
                matched_on=matched,
            )
        )

    return sorted(results, key=lambda p: p.pid)


def proc_to_dict(proc: ProcSnapshot) -> dict:
    return asdict(proc)
