"""Exportación completa del informe de auditoría."""

from __future__ import annotations

import getpass
import json
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_audit import __version__
from agent_audit.codex.analyzer import InstallationReport, report_to_dict
from agent_audit.codex.exploit_demo import collect_writable_targets
from agent_audit.codex.processes import proc_to_dict, scan_codex_processes
from agent_audit.codex.scanner import CodexInstallation
from agent_audit.common.rwx import classify_finding, classify_mode_risk, octal_to_rwx


def _enrich_permissions(perms: dict[str, Any]) -> dict[str, Any]:
    mode = perms.get("mode")
    rwx = octal_to_rwx(mode)
    risk = classify_mode_risk(mode)
    return {
        **perms,
        "rwx": rwx,
        "risk": risk,
    }


def _collect_findings(report: InstallationReport) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    for fa in report.files:
        for warning in fa.warnings:
            findings.append(
                {
                    "severity": classify_finding(warning),
                    "source": fa.path,
                    "message": warning,
                }
            )
        risk = classify_mode_risk(fa.permissions.get("mode"))
        if risk:
            findings.append(
                {
                    "severity": risk,
                    "source": fa.path,
                    "message": f"Permisos POSIX: {octal_to_rwx(fa.permissions.get('mode'))}",
                }
            )

    wr = report.workspace_restrictions
    if wr.get("sandbox_mode") == "danger-full-access":
        findings.append(
            {
                "severity": "critical",
                "source": "config",
                "message": "sandbox_mode = danger-full-access",
            }
        )
    if wr.get("approval_policy") == "never":
        findings.append(
            {
                "severity": "critical",
                "source": "config",
                "message": "approval_policy = never",
            }
        )
    for zone in wr.get("readable_zones", []):
        if zone.get("is_symlink"):
            findings.append(
                {
                    "severity": "critical",
                    "source": zone["path"],
                    "message": f"Symlink CTF → {zone.get('symlink_target')}",
                }
            )

    return findings


def installation_to_export(report: InstallationReport) -> dict[str, Any]:
    base = report_to_dict(report)
    base["all_permissions"] = [
        _enrich_permissions(p) for p in base.get("all_permissions", [])
    ]
    base["files"] = [
        {
            **f,
            "permissions": _enrich_permissions(f.get("permissions", {})),
            "findings": [
                {"severity": classify_finding(w), "message": w} for w in f.get("warnings", [])
            ],
        }
        for f in base.get("files", [])
    ]
    base["findings"] = _collect_findings(report)
    base["writable_targets"] = [
        {
            "path": str(t.path),
            "kind": t.kind,
            "codex_dir": str(t.codex_dir),
            "workspace_root": str(t.workspace_root) if t.workspace_root else None,
        }
        for t in collect_writable_targets(report)
    ]
    base["findings_summary"] = _summarize_findings(base["findings"])
    return base


def _summarize_findings(findings: list[dict[str, str]]) -> dict[str, int]:
    summary = {"critical": 0, "warn": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "info")
        if sev in summary:
            summary[sev] += 1
    return summary


def installation_entry(inst: CodexInstallation) -> dict[str, Any]:
    return {
        "kind": inst.kind,
        "codex_dir": str(inst.codex_dir),
        "workspace_root": str(inst.workspace_root) if inst.workspace_root else None,
        "markers": inst.markers,
        "label": inst.label,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def build_full_export(
    *,
    reports: list[InstallationReport],
    installations: list[CodexInstallation] | None = None,
    include_processes: bool = True,
    search_roots: list[Path] | None = None,
    full_system: bool = False,
) -> dict[str, Any]:
    processes = scan_codex_processes() if include_processes else []

    return _json_safe(
        {
            "meta": {
                "tool": "agent-audit-cli",
                "version": __version__,
                "agent": "codex",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "hostname": socket.gethostname(),
                "user": getpass.getuser(),
                "platform": platform.platform(),
                "search_roots": [str(p) for p in search_roots] if search_roots else None,
                "full_system_scan": full_system,
            },
            "installations_discovered": [
                installation_entry(i) for i in (installations or [])
            ],
            "processes": [proc_to_dict(p) for p in processes],
            "reports": [installation_to_export(r) for r in reports],
            "global_summary": _build_global_summary(reports, processes),
        }
    )


def _build_global_summary(
    reports: list[InstallationReport],
    processes: list[Any],
) -> dict[str, Any]:
    all_findings: list[dict[str, str]] = []
    writable_count = 0
    for report in reports:
        exp = installation_to_export(report)
        all_findings.extend(exp["findings"])
        writable_count += len(exp["writable_targets"])

    finding_totals = _summarize_findings(all_findings)
    return {
        "reports_count": len(reports),
        "processes_count": len(processes),
        "writable_targets_count": writable_count,
        "findings": finding_totals,
        "critical_findings": [f for f in all_findings if f.get("severity") == "critical"][:50],
        "warn_findings": [f for f in all_findings if f.get("severity") == "warn"][:50],
    }


def render_text_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    meta = payload.get("meta", {})
    lines.append("=" * 72)
    lines.append("INFORME COMPLETO — Agent Audit Codex")
    lines.append("=" * 72)
    lines.append(f"Generado: {meta.get('generated_at')}")
    lines.append(f"Host:     {meta.get('hostname')}  User: {meta.get('user')}")
    lines.append("")

    gs = payload.get("global_summary", {})
    lines.append("## Resumen global")
    lines.append(
        f"  Informes: {gs.get('reports_count')} | Procesos: {gs.get('processes_count')} | "
        f"Objetivos escribibles: {gs.get('writable_targets_count')}"
    )
    ft = gs.get("findings", {})
    lines.append(
        f"  Hallazgos: CRITICAL={ft.get('critical', 0)} WARN={ft.get('warn', 0)} INFO={ft.get('info', 0)}"
    )
    lines.append("")

    for proc in payload.get("processes", []):
        lines.append(f"## Proceso PID {proc.get('pid')}")
        lines.append(f"  cmdline: {proc.get('cmdline')}")
        lines.append(f"  cwd: {proc.get('cwd')}")
        lines.append("")

    for report in payload.get("reports", []):
        inst = report.get("installation", {})
        lines.append(f"## Instalación: {inst.get('label')}")
        lines.append(f"  codex_dir: {inst.get('codex_dir')}")
        ps = report.get("permission_summary", {})
        lines.append(
            f"  permisos: entradas={ps.get('total_entries')} "
            f"legibles={ps.get('readable')} escribibles={ps.get('writable')} "
            f"mundo-escribible={ps.get('world_writable')}"
        )

        wr = report.get("workspace_restrictions", {})
        for key in ("sandbox_mode", "approval_policy", "network_access"):
            if wr.get(key) is not None:
                lines.append(f"  {key}: {wr[key]}")

        fs = report.get("findings_summary", {})
        lines.append(
            f"  hallazgos: CRITICAL={fs.get('critical', 0)} "
            f"WARN={fs.get('warn', 0)} INFO={fs.get('info', 0)}"
        )

        for finding in report.get("findings", []):
            tag = finding.get("severity", "info").upper()
            lines.append(f"    [{tag}] {finding.get('source')}: {finding.get('message')}")

        lines.append("")
        lines.append("  ### Ficheros")
        for fa in report.get("files", []):
            perms = fa.get("permissions", {})
            rwx = perms.get("rwx", {})
            lines.append(f"  - {fa.get('path')}")
            lines.append(f"      {fa.get('description')}")
            lines.append(
                f"      usuario={rwx.get('user')} grupo={rwx.get('group')} "
                f"otros={rwx.get('other')} ({rwx.get('octal')}) "
                f"efectivo R={fa.get('readable')} W={fa.get('writable')}"
            )
            if fa.get("preview"):
                lines.append("      preview:")
                for pline in str(fa["preview"]).splitlines()[:8]:
                    lines.append(f"        | {pline}")

        if report.get("writable_targets"):
            lines.append("")
            lines.append("  ### Superficie de escalada (escribible)")
            for wt in report["writable_targets"]:
                lines.append(f"    - [{wt.get('kind')}] {wt.get('path')}")

        lines.append("")

    return "\n".join(lines)


def write_export(
    payload: dict[str, Any],
    path: Path,
    *,
    fmt: str = "json",
) -> Path:
    path = path.expanduser()
    if fmt == "json":
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    elif fmt in {"txt", "text", "md"}:
        path.write_text(render_text_report(payload), encoding="utf-8")
    else:
        raise ValueError(f"Formato no soportado: {fmt}")
    return path.resolve()
