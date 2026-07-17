#!/usr/bin/env python3
"""Reconocimiento de superficie agéntica: config, skills, comandos y permisos FS."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "codex": {
        "label": "OpenAI Codex CLI",
        "global_config_globs": [
            "~/.codex/config.toml",
            "~/.codex/ollama-launch.config.toml",
            "~/.codex/*.config.toml",
            "~/.codex/model.json",
            "~/.codex/execpolicy*",
        ],
        "project_config_globs": [
            ".codex/config.toml",
            "AGENTS.md",
        ],
        "skill_globs": [
            ".codex/skills/**/SKILL.md",
            "skills/**/SKILL.md",
        ],
        "command_globs": [
            ".codex/commands/**/*.md",
            ".codex/command/**/*.md",
        ],
        "permission_keys": [
            "approval_policy",
            "sandbox_mode",
            "default_permissions",
            "permissions",
            "sandbox_workspace_write",
        ],
    },
    "opencode": {
        "label": "OpenCode",
        "global_config_globs": [
            "~/.config/opencode/opencode.json",
            "~/.config/opencode/opencode.jsonc",
            "~/.config/opencode/tui.json",
            "/etc/opencode/opencode.json",
        ],
        "project_config_globs": [
            "opencode.json",
            "opencode.jsonc",
            ".opencode/opencode.json",
        ],
        "skill_globs": [
            ".opencode/skills/**/SKILL.md",
            ".opencode/skill/**/SKILL.md",
            "~/.config/opencode/skills/**/SKILL.md",
            "~/.config/opencode/skill/**/SKILL.md",
            "~/.claude/skills/**/SKILL.md",
            "~/.agents/skills/**/SKILL.md",
        ],
        "command_globs": [
            ".opencode/commands/**/*.md",
            ".opencode/command/**/*.md",
            "~/.config/opencode/commands/**/*.md",
            "~/.config/opencode/command/**/*.md",
        ],
        "permission_keys": ["permission", "tools", "agent"],
    },
    "claude-code": {
        "label": "Claude Code",
        "global_config_globs": [
            "~/.claude/settings.json",
            "~/.claude/settings.local.json",
            "~/.claude.json",
            "/etc/claude-code/managed-settings.json",
        ],
        "project_config_globs": [
            ".claude/settings.json",
            ".claude/settings.local.json",
            "CLAUDE.md",
            "CLAUDE.local.md",
            ".claude/rules/**",
        ],
        "skill_globs": [
            ".claude/skills/**/SKILL.md",
            "~/.claude/skills/**/SKILL.md",
        ],
        "command_globs": [
            ".claude/commands/**/*.md",
            "~/.claude/commands/**/*.md",
        ],
        "permission_keys": [
            "permissions",
            "defaultMode",
            "sandbox",
            "allowManagedPermissionRulesOnly",
        ],
    },
}

SENSITIVE_DIRS = [
    "poc-workspace/secrets",
    "poc-workspace/writable",
    "poc-workspace/symlink-trap",
]


@dataclass
class PathPermission:
    path: str
    exists: bool
    mode: str | None
    owner_uid: int | None
    owner_gid: int | None
    readable: bool | None
    writable: bool | None
    executable: bool | None
    is_symlink: bool | None
    symlink_target: str | None


def expand(path: str, workspace: Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = workspace / p
    return p


def glob_paths(pattern: str, workspace: Path) -> list[Path]:
    if pattern.startswith("~/") or pattern.startswith("~\\"):
        target = Path(pattern).expanduser()
        if "*" not in pattern:
            return [target] if target.exists() else []
        base = target.parent
        tail = pattern.split("/", 1)[-1] if "/" in pattern else pattern.split("\\", 1)[-1]
        if not base.exists():
            return []
        return sorted(base.glob(tail))

    if pattern.startswith("/"):
        target = Path(pattern)
        return [target] if target.exists() else []

    return sorted(workspace.glob(pattern))


def mode_to_octal(mode: int) -> str:
    return oct(stat.S_IMODE(mode))[-3:]


def inspect_permissions(path: Path) -> PathPermission:
    if not path.exists() and not path.is_symlink():
        return PathPermission(
            path=str(path),
            exists=False,
            mode=None,
            owner_uid=None,
            owner_gid=None,
            readable=None,
            writable=None,
            executable=None,
            is_symlink=None,
            symlink_target=None,
        )

    st = path.lstat()
    target = None
    is_symlink = path.is_symlink()
    if is_symlink:
        try:
            target = str(path.readlink())
        except OSError:
            target = "<unreadable>"

    return PathPermission(
        path=str(path),
        exists=True,
        mode=mode_to_octal(st.st_mode),
        owner_uid=st.st_uid,
        owner_gid=st.st_gid,
        readable=os.access(path, os.R_OK),
        writable=os.access(path, os.W_OK),
        executable=os.access(path, os.X_OK),
        is_symlink=is_symlink,
        symlink_target=target,
    )


def load_json_config(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_parse_error": "invalid JSON", "_path": str(path)}


def extract_permission_summary(agent: str, config_path: Path) -> dict[str, Any]:
    profile = AGENT_PROFILES[agent]
    summary: dict[str, Any] = {"source": str(config_path)}

    if config_path.suffix in {".json", ".jsonc"}:
        data = load_json_config(config_path)
        if not data:
            summary["error"] = "unreadable or invalid JSON"
            return summary
        for key in profile["permission_keys"]:
            if key in data:
                summary[key] = data[key]
        if agent == "claude-code" and "permissions" in data:
            perms = data["permissions"]
            for bucket in ("allow", "ask", "deny"):
                if bucket in perms:
                    summary[f"permissions.{bucket}"] = perms[bucket]
        if agent == "opencode" and "permission" in data:
            summary["permission_rules"] = data["permission"]
        return summary

    if config_path.suffix == ".toml":
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError:
            summary["error"] = "unreadable TOML"
            return summary
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for key in profile["permission_keys"]:
                if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
                    summary.setdefault("toml_hits", []).append(stripped)
        return summary

    return summary


def collect_section(agent: str, workspace: Path, section: str) -> list[str]:
    profile = AGENT_PROFILES[agent]
    key = {
        "config": "global_config_globs",
        "project_config": "project_config_globs",
        "skills": "skill_globs",
        "commands": "command_globs",
    }[section]

    found: list[str] = []
    for pattern in profile[key]:
        for hit in glob_paths(pattern, workspace):
            found.append(str(hit))
    return sorted(set(found))


def audit(agent: str, workspace: Path) -> dict[str, Any]:
    if agent not in AGENT_PROFILES:
        raise SystemExit(f"Agente desconocido: {agent}. Opciones: {', '.join(AGENT_PROFILES)}")

    profile = AGENT_PROFILES[agent]
    config_files = collect_section(agent, workspace, "config")
    config_files.extend(collect_section(agent, workspace, "project_config"))

    permission_summaries = []
    for cfg in config_files:
        permission_summaries.append(extract_permission_summary(agent, Path(cfg)))

    dir_perms = [
        asdict(inspect_permissions(expand(rel, workspace)))
        for rel in SENSITIVE_DIRS
    ]

    return {
        "agent": agent,
        "label": profile["label"],
        "workspace": str(workspace.resolve()),
        "config_files": config_files,
        "skills": collect_section(agent, workspace, "skills"),
        "commands": collect_section(agent, workspace, "commands"),
        "permission_summaries": permission_summaries,
        "directory_permissions": dir_perms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "agent",
        choices=sorted(AGENT_PROFILES),
        help="Agente a auditar",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Directorio raíz del PoC (por defecto: cwd)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Salida JSON (por defecto: texto legible)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    report = audit(args.agent, workspace)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print(f"=== Auditoría: {report['label']} ===")
    print(f"Workspace: {report['workspace']}\n")

    def section(title: str, items: list[str]) -> None:
        print(f"## {title} ({len(items)})")
        if not items:
            print("  (ninguno detectado)")
        for item in items:
            print(f"  - {item}")
        print()

    section("Ficheros de configuración", report["config_files"])
    section("Skills", report["skills"])
    section("Comandos / reglas", report["commands"])

    print("## Resumen de permisos en config")
    if not report["permission_summaries"]:
        print("  (sin datos)")
    else:
        for entry in report["permission_summaries"]:
            print(f"  - {entry.get('source')}")
            for k, v in entry.items():
                if k == "source":
                    continue
                print(f"      {k}: {v}")
    print()

    print("## Permisos de directorios PoC")
    for row in report["directory_permissions"]:
        print(
            f"  - {row['path']}: exists={row['exists']} mode={row['mode']} "
            f"r={row['readable']} w={row['writable']} x={row['executable']} "
            f"symlink={row['is_symlink']} -> {row['symlink_target']}"
        )


if __name__ == "__main__":
    main()
