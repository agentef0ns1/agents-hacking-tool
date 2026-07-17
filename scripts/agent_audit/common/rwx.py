"""Formato RWX usuario/grupo/otros y clasificación de riesgo."""

from __future__ import annotations

from agent_audit.common.colors import C


def octal_to_rwx(mode: str | None) -> dict[str, str]:
    if not mode or len(mode) != 3 or not mode.isdigit():
        return {"user": "---", "group": "---", "other": "---", "octal": mode or "???"}

    value = int(mode, 8)

    def triple(read_bit: int, write_bit: int, exec_bit: int) -> str:
        r = "R" if value & read_bit else "-"
        w = "W" if value & write_bit else "-"
        x = "X" if value & exec_bit else "-"
        return f"{r}{w}{x}"

    return {
        "user": triple(0o400, 0o200, 0o100),
        "group": triple(0o040, 0o020, 0o010),
        "other": triple(0o004, 0o002, 0o001),
        "octal": mode,
    }


def _color_rwx(token: str, *, scope: str) -> str:
    has_w = "W" in token
    has_x = "X" in token
    if scope == "other" and has_w:
        return C.critical(token)
    if scope == "group" and has_w:
        return C.warn(token)
    if scope == "user" and has_w and has_x:
        return C.warn(token)
    if has_w:
        return C.warn(token)
    if has_x:
        return C.info(token)
    return token


def format_rwx_line(mode: str | None, *, label: str = "perm") -> str:
    rwx = octal_to_rwx(mode)
    user = _color_rwx(rwx["user"], scope="user")
    group = _color_rwx(rwx["group"], scope="group")
    other = _color_rwx(rwx["other"], scope="other")
    return (
        f"{label}: usuario={user}  grupo={group}  otros={other}  "
        f"({C.dim(rwx['octal'])})"
    )


def classify_mode_risk(mode: str | None) -> str | None:
    if not mode:
        return None
    rwx = octal_to_rwx(mode)
    if "W" in rwx["other"]:
        return "critical"
    if mode in {"777", "666", "776", "767", "757"}:
        return "critical"
    if "W" in rwx["group"]:
        return "warn"
    if mode in {"775", "664", "772"}:
        return "warn"
    return None


def format_access_effective(readable: bool, writable: bool, executable: bool) -> str:
    parts = []
    if readable:
        parts.append(C.ok("R"))
    else:
        parts.append(C.dim("-"))
    if writable:
        parts.append(C.warn("W") if writable else C.dim("-"))
    else:
        parts.append(C.dim("-"))
    if executable:
        parts.append(C.info("X"))
    else:
        parts.append(C.dim("-"))
    return "efectivo: " + "".join(parts)


def classify_finding(message: str) -> str:
    lower = message.lower()
    critical_hints = (
        "mundo",
        "otros",
        "danger-full-access",
        "never",
        "777",
        "666",
        "escalada",
        "symlink",
        "secrets",
    )
    warn_hints = (
        "escribible",
        "laxos",
        "775",
        "664",
        "grupo",
        "world",
    )
    if any(h in lower for h in critical_hints):
        return "critical"
    if any(h in lower for h in warn_hints):
        return "warn"
    return "info"
