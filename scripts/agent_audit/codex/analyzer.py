"""Análisis de permisos, configuración y superficie de ataque Codex."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from agent_audit.codex.knowledge import (
    APPROVAL_POLICIES,
    SANDBOX_MODES,
    describe_config_key,
    describe_file,
)
from agent_audit.codex.scanner import CodexInstallation
from agent_audit.common.permissions import PathPermission, inspect_permissions, inspect_tree

TEXT_EXTENSIONS = {".toml", ".json", ".jsonl", ".md", ".txt", ".env", ".sh"}
SKIP_ANALYSIS_DIRS = {".tmp", "node_modules", ".git"}
MAX_PREVIEW_LINES = 40
MAX_JSONL_PREVIEW = 5


@dataclass
class FileAnalysis:
    path: str
    description: str
    permissions: dict[str, Any]
    readable: bool
    writable: bool
    extracted: dict[str, Any] = field(default_factory=dict)
    preview: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class InstallationReport:
    installation: dict[str, Any]
    files: list[FileAnalysis]
    all_permissions: list[dict[str, Any]]
    permission_summary: dict[str, Any]
    config_summary: dict[str, Any]
    skills: list[dict[str, Any]]
    exec_rules: list[dict[str, Any]]
    workspace_restrictions: dict[str, Any]


def _load_toml(path: Path) -> dict[str, Any] | None:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _preview_text(path: Path, *, max_lines: int = MAX_PREVIEW_LINES) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if path.suffix == ".jsonl":
        max_lines = MAX_JSONL_PREVIEW
    head = lines[:max_lines]
    suffix = f"\n... ({len(lines) - max_lines} líneas más)" if len(lines) > max_lines else ""
    return "\n".join(head) + suffix


def _extract_exec_rules_from_toml(data: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    perms = data.get("permissions")
    if isinstance(perms, dict):
        for shell, mapping in perms.items():
            if isinstance(mapping, dict):
                for pattern, decision in mapping.items():
                    rules.append(
                        {
                            "source": "config.toml",
                            "shell": shell,
                            "pattern": pattern,
                            "decision": decision,
                        }
                    )
    return rules


def _parse_execpolicy_file(path: Path) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rules

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r'^"([^"]+)"\s*=\s*"?(allow|deny|ask)"?', stripped)
        if match:
            rules.append(
                {
                    "source": str(path),
                    "shell": "bash",
                    "pattern": match.group(1),
                    "decision": match.group(2),
                }
            )
    return rules


def _extract_skills(data: dict[str, Any], base: Path) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    configs = data.get("skills", {}).get("config", [])
    if not isinstance(configs, list):
        if isinstance(configs, dict):
            configs = [configs]
        else:
            configs = []

    for entry in configs:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path", "")
        skill_path = (base / rel).resolve() if rel else None
        skill_md = None
        if skill_path and skill_path.is_dir():
            candidate = skill_path / "SKILL.md"
            if candidate.exists():
                skill_md = str(candidate)
        skills.append(
            {
                "path": rel,
                "enabled": entry.get("enabled", True),
                "resolved": str(skill_path) if skill_path else None,
                "skill_md": skill_md,
            }
        )
    return skills


def _summarize_sandbox(data: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "approval_policy",
        "sandbox_mode",
        "allow_login_shell",
        "model",
        "model_provider",
    ):
        if key in data:
            summary[key] = data[key]
            summary[f"{key}_desc"] = describe_config_key(key)
            if key == "sandbox_mode" and data[key] in SANDBOX_MODES:
                summary["sandbox_mode_risk"] = SANDBOX_MODES[data[key]]
            if key == "approval_policy" and data[key] in APPROVAL_POLICIES:
                summary["approval_policy_risk"] = APPROVAL_POLICIES[data[key]]

    sw = data.get("sandbox_workspace_write", {})
    if isinstance(sw, dict):
        for key in ("network_access", "writable_roots", "exclude_slash_tmp"):
            if key in sw:
                summary[key] = sw[key]
                summary[f"{key}_desc"] = describe_config_key(key)

    projects = data.get("projects", {})
    if isinstance(projects, dict):
        trusted = {
            path: info.get("trust_level")
            for path, info in projects.items()
            if isinstance(info, dict) and info.get("trust_level")
        }
        if trusted:
            summary["trusted_projects"] = trusted

    agent = data.get("agent", {})
    if isinstance(agent, dict) and agent:
        summary["agent"] = {
            "name": agent.get("name"),
            "model": agent.get("model"),
            "tools": [
                t.get("name")
                for t in agent.get("tools", [])
                if isinstance(t, dict) and t.get("name")
            ],
        }

    return summary


def _is_skipped_path(path: Path, codex_dir: Path) -> bool:
    try:
        rel = path.relative_to(codex_dir)
    except ValueError:
        return False
    return any(part in SKIP_ANALYSIS_DIRS for part in rel.parts)


def _collect_config_files(codex_dir: Path) -> list[Path]:
    patterns = [
        "config.toml",
        "config_backup",
        "ollama-launch.config.toml",
        "*.config.toml",
        "model.json",
        "execpolicy*",
        "history.jsonl",
        "version.json",
        "installation_id",
        "AGENTS.md",
    ]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(codex_dir.glob(pattern)))

    for sub in ("skills", "sessions", "shell_snapshots"):
        subdir = codex_dir / sub
        if subdir.is_dir():
            for path in sorted(subdir.rglob("*")):
                if path.is_file() and not _is_skipped_path(path, codex_dir):
                    files.append(path)

    for path in sorted(codex_dir.glob("*.sqlite*")):
        files.append(path)

    seen: set[str] = set()
    unique: list[Path] = []
    for path in files:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _permission_warnings(perm: PathPermission) -> list[str]:
    warnings: list[str] = []
    if not perm.exists:
        return warnings
    if perm.is_symlink:
        warnings.append(f"Symlink → {perm.symlink_target}")
    if perm.writable and perm.path.endswith((".toml", ".json")):
        warnings.append("Configuración escribible: posible escalada vía modificación.")
    if perm.mode:
        rwx_other = int(perm.mode, 8) & 0o002
        if rwx_other:
            warnings.append("Escritura para otros (otros=--W): privilegio innecesario.")
    if perm.mode and perm.mode in {"777", "666"}:
        warnings.append(f"Permisos críticos (mode {perm.mode}): mundo legible/escribible.")
    if perm.readable and "secrets" in perm.path:
        warnings.append("Ruta sensible legible.")
    return warnings


def analyze_file(path: Path) -> FileAnalysis:
    perm = inspect_permissions(path)
    perms_dict = asdict(perm)
    readable = bool(perm.readable)
    writable = bool(perm.writable)
    extracted: dict[str, Any] = {}
    preview = None
    warnings = _permission_warnings(perm)

    if readable and path.is_file():
        suffix = path.suffix.lower()
        name = path.name.lower()
        if suffix == ".toml" or name.endswith(".toml"):
            data = _load_toml(path)
            if data:
                extracted["toml"] = data
                extracted["sandbox_summary"] = _summarize_sandbox(data)
                extracted["exec_rules"] = _extract_exec_rules_from_toml(data)
                extracted["skills"] = _extract_skills(data, path.parent)
        elif suffix == ".json":
            data = _load_json(path)
            if data is not None:
                extracted["json"] = data
        elif suffix in {".md", ".txt", ".sh", ".env"} or name == "config_backup":
            preview = _preview_text(path)
        elif suffix == ".jsonl":
            preview = _preview_text(path)
            extracted["jsonl_lines"] = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
        elif "execpolicy" in name:
            extracted["exec_rules"] = _parse_execpolicy_file(path)

        if suffix in TEXT_EXTENSIONS or name == "config_backup":
            if preview is None and "toml" not in extracted and "json" not in extracted:
                preview = _preview_text(path, max_lines=15)

    return FileAnalysis(
        path=str(path),
        description=describe_file(path),
        permissions=perms_dict,
        readable=readable,
        writable=writable,
        extracted=extracted,
        preview=preview,
        warnings=warnings,
    )


def analyze_installation(installation: CodexInstallation) -> InstallationReport:
    codex_dir = installation.codex_dir
    tree_perms = inspect_tree(codex_dir)
    all_paths = {str(p.path) for p in tree_perms if p.exists}
    config_paths = _collect_config_files(codex_dir)
    for path in config_paths:
        all_paths.add(str(path.resolve()))

    if installation.workspace_root:
        agents_md = installation.workspace_root / "AGENTS.md"
        if agents_md.exists():
            all_paths.add(str(agents_md.resolve()))

    files = [
        _analyze_existing(Path(p))
        for p in sorted(all_paths)
        if not (Path(p).is_relative_to(codex_dir) and _is_skipped_path(Path(p), codex_dir))
    ]

    config_summary: dict[str, Any] = {}
    all_skills: list[dict[str, Any]] = []
    all_exec: list[dict[str, Any]] = []

    for fa in files:
        path = Path(fa.path)
        if path.is_relative_to(codex_dir) and _is_skipped_path(path, codex_dir):
            continue
        if "sandbox_summary" in fa.extracted:
            config_summary[fa.path] = fa.extracted["sandbox_summary"]
        if fa.extracted.get("skills"):
            all_skills.extend(fa.extracted["skills"])
        if fa.extracted.get("exec_rules"):
            all_exec.extend(fa.extracted["exec_rules"])

    skill_mds = sorted(
        p for p in codex_dir.rglob("SKILL.md") if not _is_skipped_path(p, codex_dir)
    )
    seen_skill_md: set[str] = set()
    for skill_md in skill_mds:
        key = str(skill_md.resolve())
        if key in seen_skill_md:
            continue
        seen_skill_md.add(key)
        if not any(s.get("skill_md") == key for s in all_skills):
            all_skills.append(
                {
                    "path": str(skill_md.relative_to(codex_dir)),
                    "enabled": None,
                    "resolved": str(skill_md.parent),
                    "skill_md": key,
                }
            )

    perm_stats = {
        "total_entries": len(tree_perms),
        "readable": sum(1 for p in tree_perms if p.readable),
        "writable": sum(1 for p in tree_perms if p.writable),
        "symlinks": sum(1 for p in tree_perms if p.is_symlink),
        "world_writable": sum(1 for p in tree_perms if p.mode in {"777", "666", "776", "767"}),
    }

    workspace_restrictions = _build_workspace_restrictions(config_summary, installation)

    return InstallationReport(
        installation={
            "kind": installation.kind,
            "codex_dir": str(codex_dir),
            "workspace_root": str(installation.workspace_root) if installation.workspace_root else None,
            "markers": installation.markers,
            "label": installation.label,
        },
        files=files,
        all_permissions=[asdict(p) for p in tree_perms],
        permission_summary=perm_stats,
        config_summary=config_summary,
        skills=all_skills,
        exec_rules=all_exec,
        workspace_restrictions=workspace_restrictions,
    )


def _analyze_existing(path: Path) -> FileAnalysis:
    if path.exists() or path.is_symlink():
        return analyze_file(path)
    perm = inspect_permissions(path)
    return FileAnalysis(
        path=str(path),
        description=describe_file(path),
        permissions=asdict(perm),
        readable=False,
        writable=False,
        warnings=["Fichero no encontrado."],
    )


def _build_workspace_restrictions(
    config_summary: dict[str, Any],
    installation: CodexInstallation,
) -> dict[str, Any]:
    restrictions: dict[str, Any] = {
        "workspace_root": str(installation.workspace_root) if installation.workspace_root else None,
        "sandbox_mode": None,
        "approval_policy": None,
        "network_access": None,
        "writable_roots": [],
        "readable_zones": [],
        "writable_zones": [],
    }

    for summary in config_summary.values():
        for key in ("sandbox_mode", "approval_policy", "network_access", "writable_roots"):
            if summary.get(key) is not None:
                restrictions[key] = summary[key]

    if installation.workspace_root:
        root = Path(installation.workspace_root)
        for rel in ("poc-workspace/writable", "poc-workspace/secrets", "poc-workspace/symlink-trap"):
            target = root / rel
            if target.exists() or target.is_symlink():
                perm = inspect_permissions(target)
                zone = {
                    "path": str(target),
                    "mode": perm.mode,
                    "readable": perm.readable,
                    "writable": perm.writable,
                    "is_symlink": perm.is_symlink,
                    "symlink_target": perm.symlink_target,
                }
                restrictions["readable_zones"].append(zone)
                if perm.writable:
                    restrictions["writable_zones"].append(zone)

    return restrictions


def report_to_dict(report: InstallationReport) -> dict[str, Any]:
    return {
        "installation": report.installation,
        "all_permissions": report.all_permissions,
        "permission_summary": report.permission_summary,
        "config_summary": report.config_summary,
        "skills": report.skills,
        "exec_rules": report.exec_rules,
        "workspace_restrictions": report.workspace_restrictions,
        "files": [
            {
                "path": f.path,
                "description": f.description,
                "permissions": f.permissions,
                "readable": f.readable,
                "writable": f.writable,
                "extracted": f.extracted,
                "preview": f.preview,
                "warnings": f.warnings,
            }
            for f in report.files
        ],
    }
