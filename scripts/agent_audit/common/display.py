"""Formateo de informes en terminal con colores y permisos RWX."""

from __future__ import annotations

import json
from typing import Any

from agent_audit.codex.analyzer import InstallationReport
from agent_audit.codex.processes import ProcSnapshot
from agent_audit.common.colors import C
from agent_audit.common.rwx import (
    classify_finding,
    classify_mode_risk,
    format_access_effective,
    format_rwx_line,
)


def _center_block(text: str, width: int) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(
        " " * max(0, (width - len(line)) // 2) + line for line in lines
    )


def print_banner() -> None:
    banner = """\
  ╔══════════════════════════════════════════════╗
  ║                  F 0 n s 1                   ║
  ║              Offensive Security              ║
  ║     Agent Hacking Tools - Surface Auditor    ║
  ╚══════════════════════════════════════════════╝"""
    banner_width = max(len(line) for line in banner.splitlines())

    skull_raw = """\
      .-"      "-.
     /            \\
    |              |
    |,  .-.  .-.  ,|
    | )(_ /  \\_ )( |
    |/     /\\     \\|
    (_     ^^     _)
     \\__|IIIIII|__/
    | \\IIIIII/ |
    \\________/"""
    skull = _center_block(skull_raw, banner_width)
    print(C.banner(f"\n{skull}\n{banner}\n"))


def _emit_finding(message: str) -> None:
    level = classify_finding(message)
    if level == "critical":
        print(f"    {C.critical('[CRITICAL]')} {C.critical(message)}")
    elif level == "warn":
        print(f"    {C.warn('[WARN]')} {C.warn(message)}")
    else:
        print(f"    {C.info('[INFO]')} {message}")


def print_header(title: str, *, width: int = 72) -> None:
    short = title if len(title) <= width else title[: width - 3] + "..."
    line = C.dim("=" * min(len(short), width))
    print(f"\n{line}\n{C.bold(short) if hasattr(C, 'bold') else short}\n{line}")


def _sandbox_risk(value: str | None) -> None:
    if value == "danger-full-access":
        print(f"  sandbox_mode: {C.critical(value)} — acceso amplio al SO")
    elif value:
        print(f"  sandbox_mode: {C.info(str(value))}")


def _approval_risk(value: str | None) -> None:
    if value == "never":
        print(f"  approval_policy: {C.critical(value)} — sin confirmación humana")
    elif value:
        print(f"  approval_policy: {C.warn(str(value))}")


def print_installation_report(report: InstallationReport, *, verbose: bool = False) -> None:
    inst = report.installation
    print_header(f"Auditoría Codex — {inst['label']}")
    print(f"Directorio .codex: {C.info(inst['codex_dir'])}")
    if inst.get("workspace_root"):
        print(f"Workspace raíz:    {inst['workspace_root']}")
    if inst.get("markers"):
        print(f"Marcadores:        {', '.join(inst['markers'])}")

    ps = report.permission_summary
    print(f"\n{C.bold('## Resumen de permisos')}")
    print(
        f"  Entradas: {ps['total_entries']} | legibles: {ps['readable']} | "
        f"escribibles: {ps['writable']} | symlinks: {ps['symlinks']} | "
        f"mundo-escribible: {C.critical(str(ps['world_writable'])) if ps['world_writable'] else C.ok('0')}"
    )
    if ps["world_writable"]:
        _emit_finding(f"{ps['world_writable']} ficheros con escritura para otros (otros=--W)")
    if ps["total_entries"] > len(report.files):
        print(
            C.dim(
                f"  (árbol: {ps['total_entries']} nodos; "
                f"analizados: {len(report.files)} ficheros relevantes)"
            )
        )

    if report.workspace_restrictions:
        wr = report.workspace_restrictions
        print("\n## Restricciones de workspace")
        _sandbox_risk(wr.get("sandbox_mode"))
        _approval_risk(wr.get("approval_policy"))
        if wr.get("network_access") is True:
            print(f"  network_access: {C.critical('true')}")
        elif wr.get("network_access") is not None:
            print(f"  network_access: {wr['network_access']}")
        if wr.get("writable_roots"):
            print(f"  writable_roots: {C.warn(str(wr['writable_roots']))}")
        for zone in wr.get("readable_zones", []):
            risk = classify_mode_risk(zone.get("mode"))
            zone_line = (
                f"  zona {zone['path']}: {format_rwx_line(zone.get('mode'))} "
                f"symlink={zone['is_symlink']}"
            )
            if risk == "critical":
                print(C.critical(zone_line))
            elif risk == "warn":
                print(C.warn(zone_line))
            else:
                print(zone_line)
            if zone.get("is_symlink"):
                _emit_finding(f"Symlink CTF → {zone.get('symlink_target')}")

    if report.config_summary:
        print("\n## Configuración extraída")
        for source, summary in report.config_summary.items():
            print(f"  {C.info('[' + source + ']')}")
            for key, value in summary.items():
                if key.endswith("_desc") or key.endswith("_risk"):
                    continue
                if key == "sandbox_mode" and value == "danger-full-access":
                    print(f"    {key}: {C.critical(str(value))}")
                elif key == "approval_policy" and value == "never":
                    print(f"    {key}: {C.critical(str(value))}")
                elif isinstance(value, (dict, list)) and not verbose:
                    print(f"    {key}: {json.dumps(value, ensure_ascii=False)[:120]}...")
                else:
                    print(f"    {key}: {value}")
            for key in sorted(summary):
                if key.endswith("_risk"):
                    _emit_finding(str(summary[key]))

    writable_configs = [f for f in report.files if f.writable and ".toml" in f.path]
    if writable_configs:
        print(f"\n{C.warn('## Superficie de escalada')}")
        for fa in writable_configs[:5]:
            _emit_finding(f"Config escribible: {fa.path}")

    if report.skills:
        print(f"\n## Skills ({len(report.skills)})")
        for skill in report.skills[:15 if not verbose else len(report.skills)]:
            status = "enabled" if skill.get("enabled") else "disabled" if skill.get("enabled") is False else "?"
            label = C.ok(status) if status == "enabled" else status
            print(f"  - {skill.get('path')} [{label}]")
            if skill.get("skill_md") and verbose:
                print(f"      SKILL.md: {skill['skill_md']}")
        if not verbose and len(report.skills) > 15:
            print(C.dim(f"  ... y {len(report.skills) - 15} skills más"))

    if report.exec_rules:
        print(f"\n## Reglas de ejecución ({len(report.exec_rules)})")
        for rule in report.exec_rules:
            decision = rule.get("decision")
            styled = C.critical(decision) if decision == "allow" and rule.get("pattern") == "*" else decision
            print(
                f"  - {rule.get('pattern')} → {styled} "
                f"(shell={rule.get('shell')})"
            )
    else:
        print("\n## Reglas de ejecución")
        print(C.dim("  (ninguna detectada en config ni execpolicy)"))

    print(f"\n## Ficheros analizados ({len(report.files)})")
    show_files = report.files if verbose else report.files[:30]
    for fa in show_files:
        perm = fa.permissions
        print(f"\n  • {fa.path}")
        print(f"    {C.dim(fa.description)}")
        if perm.get("exists"):
            print(f"    {format_rwx_line(perm.get('mode'))}")
            print(
                f"    {format_access_effective(fa.readable, fa.writable, bool(perm.get('executable')))}  "
                f"type={perm.get('file_type')}"
            )
            risk = classify_mode_risk(perm.get("mode"))
            if risk == "critical":
                _emit_finding("Privilegios innecesarios: escritura para otros o modo 777/666")
            elif risk == "warn" and fa.writable:
                _emit_finding("Permisos amplios: escritura para grupo o config mutable")
        else:
            print(C.dim("    (no existe)"))
        for warning in fa.warnings:
            _emit_finding(warning)

        if verbose and fa.preview:
            print(C.dim("    --- preview ---"))
            for line in fa.preview.splitlines()[:20]:
                print(C.dim(f"    | {line}"))

    if not verbose and len(report.files) > 30:
        print(C.dim(f"\n  ... y {len(report.files) - 30} ficheros más (use -v/--verbose)"))


def print_discovery(installations: list[Any]) -> None:
    print_header("Instalaciones Codex detectadas")
    if not installations:
        print(C.warn("  (ninguna)"))
        return
    for idx, inst in enumerate(installations, 1):
        kind = C.critical(inst.kind) if inst.kind == "global" else C.info(inst.kind)
        print(f"  {idx}. [{kind}] {inst.codex_dir}")
        if inst.workspace_root and inst.kind == "workspace":
            print(f"      workspace: {inst.workspace_root}")
        if inst.markers:
            print(f"      markers: {', '.join(inst.markers)}")


def print_process_report(processes: list[ProcSnapshot]) -> None:
    print_header("Procesos Codex en ejecución")
    if not processes:
        print(C.warn("  No hay procesos Codex activos en el sistema."))
        print(C.dim("  Busca: codex, @openai/codex, ollama launch codex"))
        return

    for proc in processes:
        print(f"\n  {C.ok('PID')} {proc.pid}  match={proc.matched_on}")
        print(f"    cmdline: {proc.cmdline[:120]}")
        if proc.name:
            print(f"    Name: {proc.name}  State: {proc.state}")
        if proc.ppid is not None:
            print(f"    PPID: {proc.ppid}  UID: {proc.uid}  GID: {proc.gid}")
        if proc.vm_rss_kb:
            print(f"    VmRSS: {proc.vm_rss_kb} kB  FDs abiertos: {proc.open_fds}")
        if proc.cwd:
            print(f"    cwd: {C.info(proc.cwd)}")
        if proc.environ:
            print("    environ (relevante):")
            for key, value in sorted(proc.environ.items()):
                line = f"      {key}={value}"
                if "codex" in key.lower() or key in {"HOME", "PWD", "OLLAMA_HOST"}:
                    print(C.warn(line))
                else:
                    print(C.dim(line))
