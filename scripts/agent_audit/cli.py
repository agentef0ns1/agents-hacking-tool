"""CLI interactiva de auditoría de agentes — Codex."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_audit.codex.analyzer import analyze_installation
from agent_audit.codex.exploit_demo import DEMO_ACTIONS, collect_writable_targets
from agent_audit.codex.processes import scan_codex_processes
from agent_audit.common.export import build_full_export, render_text_report, write_export
from agent_audit.codex.scanner import CodexInstallation, discover_codex_installations
from agent_audit.common.colors import C
from agent_audit.common.display import (
    print_banner,
    print_discovery,
    print_header,
    print_installation_report,
    print_process_report,
)


class AuditSession:
    def __init__(self) -> None:
        self.search_roots: list[Path] = []
        self.installations: list[CodexInstallation] = []
        self.reports = []
        self.last_report = None
        self.full_system = False
        self.processes = []

    def discover(self) -> None:
        print(C.info("\n⏳ Escaneando sistema en busca de .codex ..."))
        roots = self.search_roots or None
        self.installations = discover_codex_installations(
            roots,
            full_system=self.full_system,
        )
        print_discovery(self.installations)
        print(f"\nTotal: {len(self.installations)} instalación(es).")

    def audit_home(self, *, show: bool = True) -> None:
        home_codex = Path.home() / ".codex"
        if not home_codex.is_dir():
            print(C.critical(f"\n✗ No existe {home_codex}"))
            return
        inst = CodexInstallation(
            kind="global",
            codex_dir=home_codex.resolve(),
            markers=["$HOME/.codex"],
        )
        self._audit_one(inst, show=show)

    def audit_workspace(self, path: str, *, show: bool = True) -> None:
        workspace = Path(path).expanduser().resolve()
        codex_dir = workspace / ".codex"
        if not codex_dir.is_dir():
            print(C.critical(f"\n✗ No hay .codex en {workspace}"))
            return
        inst = CodexInstallation(
            kind="workspace",
            codex_dir=codex_dir.resolve(),
            workspace_root=workspace,
        )
        self._audit_one(inst, show=show)

    def audit_full(self) -> None:
        self.discover()
        if not self.installations:
            return
        self.reports.clear()
        for inst in self.installations:
            self._audit_one(inst, show=False)
        print_header(f"Auditoría completa — {len(self.reports)} informe(s)")
        for report in self.reports:
            print_installation_report(report, verbose=False)
            print()

    def audit_processes(self) -> None:
        print(C.info("\n⏳ Buscando procesos Codex en /proc ..."))
        self.processes = scan_codex_processes()
        print_process_report(self.processes)

    def exploit_demo(self) -> None:
        if not self.last_report:
            print(C.warn("\nEjecute primero una auditoría (opciones 1-3)."))
            return

        targets = collect_writable_targets(self.last_report)
        if not targets:
            print(C.ok("\n✓ Sin superficie de escritura en config/skills detectada."))
            return

        print_header("Demostración de escalada — config/skills escribibles")
        print(C.warn("  LAB AUTORIZADO §6.1.4 — modifica ficheros reales con backup."))
        print("\n  Objetivos escribibles:")
        for idx, target in enumerate(targets, 1):
            print(f"    {idx}. [{target.kind}] {target.path}")

        print("\n  Vectores de demostración:")
        for key, (label, kind, _) in DEMO_ACTIONS.items():
            print(f"    {key}. {label}")

        choice = input("\n  Vector (vacío=cancelar): ").strip()
        if not choice or choice not in DEMO_ACTIONS:
            print(C.dim("  Cancelado."))
            return

        label, required_kind, action_fn = DEMO_ACTIONS[choice]
        matching = [t for t in targets if t.kind == required_kind or (required_kind == "config" and t.kind == "config")]
        if required_kind == "skill":
            matching = [t for t in targets if t.kind == "skill_dir"]
        elif required_kind == "agents":
            matching = [t for t in targets if t.kind == "agents"]
        elif required_kind == "config":
            matching = [t for t in targets if t.kind == "config"]

        if not matching:
            print(C.critical(f"\n✗ No hay objetivo escribible de tipo '{required_kind}'."))
            return

        target = matching[0]
        if len(matching) > 1:
            print("\n  Seleccione objetivo:")
            for idx, t in enumerate(matching, 1):
                print(f"    {idx}. {t.path}")
            pick = input("  Número: ").strip()
            if pick.isdigit() and 1 <= int(pick) <= len(matching):
                target = matching[int(pick) - 1]

        print(C.critical(f"\n  ATENCIÓN: se modificará {target.path}"))
        confirm = input("  Escriba CONFIRMO para continuar: ").strip()
        if confirm != "CONFIRMO":
            print(C.dim("  Abortado."))
            return

        try:
            result = action_fn(target)
            if result.get("injected") is False:
                print(C.warn("\n⚠ Demostración no aplicada (sin cambios en disco):"))
            else:
                print(C.ok("\n✓ Demostración aplicada:"))
            for key, value in result.items():
                if key == "impact":
                    print(f"    {C.critical('impact')}: {value}")
                elif key == "rules_applied":
                    print(f"    {C.warn('rules_applied')}:")
                    for pattern, decision in value.items():
                        print(f"      \"{pattern}\" = \"{decision}\"")
                else:
                    print(f"    {key}: {value}")
            if result.get("injected") is not False:
                print(C.warn("\n  Relance Codex para cargar la nueva configuración."))
        except OSError as exc:
            print(C.critical(f"\n✗ Error al escribir: {exc}"))

    def _audit_one(self, installation: CodexInstallation, *, show: bool = True) -> None:
        print(C.info(f"\n⏳ Analizando {installation.codex_dir} ..."))
        report = analyze_installation(installation)
        self.reports.append(report)
        self.last_report = report
        if show:
            print_installation_report(report, verbose=False)

    def configure_roots(self) -> None:
        raw = input(
            "\nRutas de búsqueda (separadas por espacio, vacío=por defecto, '/'=sistema): "
        ).strip()
        if not raw:
            self.search_roots = []
            self.full_system = False
            print(C.dim("  → Rutas por defecto: $HOME, /opt, /srv, /media, /mnt"))
            return
        if raw.lower() in {"/", "full", "sistema", "system"}:
            self.full_system = True
            self.search_roots = []
            print(C.warn("  → Escaneo de sistema completo (puede tardar)"))
            return
        self.full_system = False
        self.search_roots = [Path(p) for p in raw.split()]
        print(f"  → Rutas: {', '.join(str(p) for p in self.search_roots)}")

    def export_full_report(self, path: str | None = None, fmt: str = "json") -> None:
        if not self.reports:
            print(C.warn("\nSin informes — ejecute una auditoría (opciones 1-3) antes de exportar."))
            return

        if not self.processes:
            self.processes = scan_codex_processes()

        payload = build_full_export(
            reports=self.reports,
            installations=self.installations or None,
            include_processes=True,
            search_roots=self.search_roots or None,
            full_system=self.full_system,
        )

        if path:
            out = write_export(payload, Path(path), fmt=fmt)
            print(C.ok(f"\n✓ Informe completo exportado → {out}"))
            gs = payload.get("global_summary", {})
            ft = gs.get("findings", {})
            print(
                f"  Informes: {gs.get('reports_count')} | "
                f"CRITICAL: {ft.get('critical', 0)} | WARN: {ft.get('warn', 0)} | "
                f"Procesos: {gs.get('processes_count')}"
            )
            return

        if fmt in {"txt", "text", "md"}:
            print(render_text_report(payload))
        else:
            print(json.dumps(payload, indent=2, ensure_ascii=False))

    def export_json(self, path: str | None = None) -> None:
        self.export_full_report(path, fmt="json")

    def _interactive_export(self) -> None:
        print_header("Exportar informe completo")
        print("  Formatos: json | txt")
        fmt = input("  Formato [json]: ").strip().lower() or "json"
        path = input("  Ruta de salida (vacío = stdout): ").strip() or None
        if path and "." not in Path(path).name:
            ext = "json" if fmt == "json" else "txt"
            path = f"{path}.{ext}"
        self.export_full_report(path, fmt=fmt)


def interactive_loop(session: AuditSession) -> None:
    print_banner()
    menu = {
        "1": ("Auditar $HOME/.codex", lambda: session.audit_home()),
        "2": (
            "Auditar workspace .codex",
            lambda: session.audit_workspace(
                input("\nRuta del workspace (directorio padre de .codex): ").strip()
            ),
        ),
        "3": ("Auditoría completa", lambda: session.audit_full()),
        "4": ("Procesos Codex en ejecución (/proc)", lambda: session.audit_processes()),
        "5": ("Demostración escalada (config/skills escribibles)", lambda: session.exploit_demo()),
        "6": ("Configurar rutas de búsqueda", lambda: session.configure_roots()),
        "7": (
            "Exportar informe completo",
            lambda: session._interactive_export(),
        ),
    }

    while True:
        print(f"\n{C.bold('--- Menú ---')}")
        for key, (label, _) in menu.items():
            print(f"  {key}. {label}")
        print(C.dim("  q. Salir"))
        choice = input("\nOpción: ").strip().lower()
        if choice in {"q", "quit", "salir", "0"}:
            print(C.dim("Hasta luego."))
            break
        action = menu.get(choice)
        if not action:
            print(C.warn("Opción no válida."))
            continue
        _, fn = action
        try:
            fn()
        except KeyboardInterrupt:
            print(C.dim("\n(interrumpido)"))
        except Exception as exc:
            print(C.critical(f"\n✗ Error: {exc}"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auditoría interactiva de agentes Codex — permisos, config, skills.",
    )
    parser.add_argument("agent", nargs="?", default="codex", choices=["codex"])
    parser.add_argument("--scan", action="store_true", help="Escanear .codex en el sistema")
    parser.add_argument("--home", action="store_true", help="Auditar $HOME/.codex")
    parser.add_argument("--workspace", metavar="PATH", help="Auditar .codex de un workspace")
    parser.add_argument("--full", action="store_true", help="Descubrir y auditar todo")
    parser.add_argument("--processes", action="store_true", help="Listar procesos Codex")
    parser.add_argument(
        "--roots",
        nargs="+",
        metavar="DIR",
        help="Rutas extra para el descubrimiento",
    )
    parser.add_argument(
        "--full-system",
        action="store_true",
        help="Escanear desde / (lento; excluye /proc, /sys, etc.)",
    )
    parser.add_argument("--json", action="store_true", help="Exportar informe completo JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Fichero de salida del informe")
    parser.add_argument(
        "--format",
        choices=["json", "txt", "text", "md"],
        default="json",
        help="Formato de exportación (con --json o -o)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Informe detallado")
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="No abrir menú (requiere --scan, --home, --workspace o --full)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    session = AuditSession()
    if args.roots:
        session.search_roots = [Path(r) for r in args.roots]
    session.full_system = args.full_system

    has_action = args.scan or args.home or args.workspace or args.full or args.processes

    if has_action:
        quiet = args.no_interactive or args.json or bool(args.output)
        if args.scan:
            session.discover()
        if args.home:
            session.audit_home(show=not quiet)
        if args.workspace:
            session.audit_workspace(args.workspace, show=not quiet)
        if args.full:
            session.audit_full()
        if args.processes:
            session.audit_processes()

        if args.json or args.output:
            session.export_full_report(args.output, fmt=args.format)
        elif session.last_report and not args.full and not args.processes:
            print_installation_report(session.last_report, verbose=args.verbose)
        elif args.full and args.verbose:
            for report in session.reports:
                print_installation_report(report, verbose=True)
        return 0

    if args.no_interactive:
        parser.error("Con --no-interactive indique --scan, --home, --workspace o --full")

    try:
        interactive_loop(session)
    except KeyboardInterrupt:
        print(C.dim("\nHasta luego."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
