#!/usr/bin/env python3
"""Genera ~/.codex/ollama-launch.config.toml y model.json para Codex + Ollama."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def ollama_context_length(model: str, base_url: str) -> int:
    api_base = base_url.rstrip("/")
    payload = json.dumps({"model": model}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}/api/show",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            out = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        out = ""

    if not out and _ollama_cli_available():
        try:
            out = subprocess.check_output(
                ["ollama", "show", model],
                stderr=subprocess.STDOUT,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 128_000

    match = re.search(r"context length\s+(\d+)", out, re.IGNORECASE)
    if match:
        return int(match.group(1))

    try:
        data = json.loads(out)
        for key in ("model_info", "details"):
            block = data.get(key) if isinstance(data, dict) else None
            if isinstance(block, dict):
                for ctx_key in ("context_length", "num_ctx"):
                    if ctx_key in block:
                        return int(block[ctx_key])
    except json.JSONDecodeError:
        pass

    return 128_000


def _ollama_cli_available() -> bool:
    try:
        subprocess.run(
            ["ollama", "--version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def ollama_model_exists(model: str, base_url: str) -> bool:
    api_base = base_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{api_base}/api/tags", timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = {item.get("name", "") for item in data.get("models", [])}
        if model in models:
            return True
        if not model.endswith(":latest"):
            return f"{model}:latest" in models
        return False
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass

    if not _ollama_cli_available():
        return False

    try:
        subprocess.run(
            ["ollama", "show", model],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def main() -> None:
    model = (sys.argv[1] if len(sys.argv) > 1 else "phi4-mini:latest").strip()
    base_url = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:11434").rstrip("/")
    project_root = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else Path.cwd()

    codex_dir = Path.home() / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = codex_dir / "model.json"
    profile_path = codex_dir / "ollama-launch.config.toml"
    provider_base_url = f"{base_url}/v1/"

    context = ollama_context_length(model, base_url)
    catalog = {
        "models": [
            {
                "slug": model,
                "display_name": model,
                "context_window": context,
                "shell_type": "default",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 0,
                "truncation_policy": {"mode": "bytes", "limit": 10000},
                "input_modalities": ["text"],
                "base_instructions": "",
                "support_verbosity": True,
                "default_verbosity": "low",
                "supports_parallel_tool_calls": False,
                "supports_reasoning_summaries": False,
                "supported_reasoning_levels": [],
                "experimental_supported_tools": [],
            }
        ]
    }
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    profile = f'''model = "{model}"
model_provider = "ollama-launch"
model_catalog_json = "{catalog_path}"
model_reasoning_effort = "none"

[model_providers.ollama-launch]
name = "Ollama"
base_url = "{provider_base_url}"
wire_api = "responses"

[projects."{project_root}"]
trust_level = "trusted"
'''
    profile_path.write_text(profile, encoding="utf-8")
    print(f"Perfil Codex escrito: {profile_path}")
    print(f"Catálogo de modelos: {catalog_path}")
    print(f"Ollama remoto: {provider_base_url}")

    if ollama_model_exists(model, base_url):
        print(f"Modelo '{model}' disponible en {base_url}.")
    else:
        print(
            f"Aviso: no se pudo confirmar el modelo '{model}' en {base_url}.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
