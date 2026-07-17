"""Colores ANSI para la consola (warn=amarillo, critical=rojo)."""

from __future__ import annotations

import os
import sys


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"

    def __init__(self, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
        self.enabled = enabled

    def wrap(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"{code}{text}{self.RESET}"

    def info(self, text: str) -> str:
        return self.wrap(text, self.CYAN)

    def ok(self, text: str) -> str:
        return self.wrap(text, self.GREEN)

    def warn(self, text: str) -> str:
        return self.wrap(text, self.YELLOW + self.BOLD)

    def critical(self, text: str) -> str:
        return self.wrap(text, self.RED + self.BOLD)

    def banner(self, text: str) -> str:
        return self.wrap(text, self.MAGENTA + self.BOLD)

    def bold(self, text: str) -> str:
        return self.wrap(text, self.BOLD)


    def dim(self, text: str) -> str:
        return self.wrap(text, self.DIM)


C = Colors()
