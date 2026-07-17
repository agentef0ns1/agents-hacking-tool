"""Descubrimiento de instalaciones y workspaces Codex en el sistema."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_SEARCH_ROOTS = [
    Path.home(),
    Path("/opt"),
    Path("/srv"),
    Path("/media"),
    Path("/mnt"),
]

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".npm",
    ".cache",
    ".local/share/Trash",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    "proc",
    "sys",
    "dev",
    "run",
    "snap",
}

CODEX_DIR_NAME = ".codex"
WORKSPACE_MARKERS = ("AGENTS.md", "config.toml")


@dataclass
class CodexInstallation:
    kind: str  # "global" | "workspace"
    codex_dir: Path
    workspace_root: Path | None = None
    markers: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.kind == "global":
            return f"Global: {self.codex_dir}"
        root = self.workspace_root or self.codex_dir.parent
        return f"Workspace: {root} → {self.codex_dir}"


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.startswith(".npm")


def discover_with_walk(roots: list[Path], *, max_depth: int = 12) -> list[CodexInstallation]:
    found: dict[str, CodexInstallation] = {}
    home_codex = Path.home() / CODEX_DIR_NAME

    if home_codex.is_dir():
        found[str(home_codex.resolve())] = CodexInstallation(
            kind="global",
            codex_dir=home_codex.resolve(),
            workspace_root=None,
            markers=["$HOME/.codex"],
        )

    for root in roots:
        root = root.expanduser().resolve()
        if not root.exists() or not root.is_dir():
            continue

        base_depth = len(root.parts)
        for dirpath, dirnames, _ in os.walk(root, topdown=True, followlinks=False):
            current = Path(dirpath)
            depth = len(current.parts) - base_depth
            if depth > max_depth:
                dirnames.clear()
                continue

            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

            if CODEX_DIR_NAME not in dirnames:
                continue

            codex_path = (current / CODEX_DIR_NAME).resolve()
            key = str(codex_path)
            if key in found:
                continue

            markers = []
            workspace_root = current.resolve()
            for marker in WORKSPACE_MARKERS:
                if (workspace_root / marker).exists():
                    markers.append(marker)
                if (codex_path / marker.replace("AGENTS.md", "config.toml")).exists() and marker == "config.toml":
                    markers.append(".codex/config.toml")

            kind = "workspace" if workspace_root != Path.home() else "global"
            if codex_path == home_codex.resolve():
                kind = "global"

            found[key] = CodexInstallation(
                kind=kind,
                codex_dir=codex_path,
                workspace_root=workspace_root if kind == "workspace" else None,
                markers=markers,
            )

    return sorted(found.values(), key=lambda x: (x.kind != "global", str(x.codex_dir)))


def discover_with_find(roots: list[Path], *, timeout: int = 120) -> list[CodexInstallation]:
    """Búsqueda rápida con find(1) cuando está disponible."""
    prune = " -o ".join(f"-name '{name}' -prune" for name in sorted(SKIP_DIR_NAMES))
    installations: dict[str, CodexInstallation] = {}

    home_codex = Path.home() / CODEX_DIR_NAME
    if home_codex.is_dir():
        installations[str(home_codex.resolve())] = CodexInstallation(
            kind="global",
            codex_dir=home_codex.resolve(),
            markers=["$HOME/.codex"],
        )

    for root in roots:
        root = root.expanduser().resolve()
        if not root.exists():
            continue
        cmd = (
            f"find '{root}' \\( {prune} \\) -o "
            f"-type d -name '{CODEX_DIR_NAME}' -print 2>/dev/null"
        )
        try:
            proc = subprocess.run(
                ["bash", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (subprocess.TimeoutExpired, OSError):
            return discover_with_walk(roots)

        for line in proc.stdout.splitlines():
            codex_path = Path(line.strip()).resolve()
            key = str(codex_path)
            if key in installations:
                continue
            workspace_root = codex_path.parent
            kind = "global" if codex_path == home_codex.resolve() else "workspace"
            markers = [m for m in WORKSPACE_MARKERS if (workspace_root / m).exists()]
            installations[key] = CodexInstallation(
                kind=kind,
                codex_dir=codex_path,
                workspace_root=workspace_root if kind == "workspace" else None,
                markers=markers,
            )

    return sorted(installations.values(), key=lambda x: (x.kind != "global", str(x.codex_dir)))


def discover_codex_installations(
    roots: list[Path] | None = None,
    *,
    use_find: bool = True,
    full_system: bool = False,
) -> list[CodexInstallation]:
    if full_system:
        search_roots = [Path("/")]
    elif roots:
        search_roots = [Path(r) for r in roots]
    else:
        search_roots = list(DEFAULT_SEARCH_ROOTS)

    if use_find:
        return discover_with_find(search_roots)
    return discover_with_walk(search_roots)
