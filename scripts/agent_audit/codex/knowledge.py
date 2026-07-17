"""Base de conocimiento: descripciones de ficheros y claves de configuración Codex."""

from __future__ import annotations

import re
from pathlib import Path

# Patrones → descripción breve (orden: más específico primero)
FILE_DESCRIPTIONS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"ollama-launch\.config\.toml$"),
        "Perfil Ollama: modelo, provider, trust de proyectos y herramientas del agente.",
    ),
    (
        re.compile(r"config\.toml$"),
        "Configuración principal: sandbox, approval_policy, skills y permisos exec.",
    ),
    (
        re.compile(r"execpolicy"),
        "Política de ejecución shell: comandos permitidos (allow), denegados (deny) o con pregunta (ask).",
    ),
    (
        re.compile(r"model\.json$"),
        "Catálogo de modelos: context window, modalidades y truncado.",
    ),
    (
        re.compile(r"history\.jsonl$"),
        "Historial de interacciones del usuario con Codex (JSONL).",
    ),
    (
        re.compile(r"sessions/.+\.jsonl$"),
        "Rollout de sesión: mensajes, tool calls y decisiones de aprobación.",
    ),
    (
        re.compile(r"logs_\d+\.sqlite"),
        "Logs persistentes de actividad del agente (SQLite).",
    ),
    (
        re.compile(r"state_\d+\.sqlite"),
        "Estado interno del agente: contexto y metadatos de sesión.",
    ),
    (
        re.compile(r"memories_\d+\.sqlite"),
        "Memoria persistente del agente (recuerdos entre sesiones).",
    ),
    (
        re.compile(r"goals_\d+\.sqlite"),
        "Objetivos/tareas persistentes del agente.",
    ),
    (
        re.compile(r"shell_snapshots"),
        "Instantáneas del entorno shell capturadas por Codex.",
    ),
    (
        re.compile(r"skills/.+/SKILL\.md$"),
        "Skill del agente: instrucciones, herramientas y restricciones invocables.",
    ),
    (
        re.compile(r"AGENTS\.md$"),
        "Instrucciones de proyecto: reglas del workspace que el agente carga al iniciar.",
    ),
    (
        re.compile(r"config_backup$"),
        "Copia de respaldo de config.toml del workspace.",
    ),
    (
        re.compile(r"version\.json$"),
        "Versión instalada del CLI Codex.",
    ),
    (
        re.compile(r"installation_id$"),
        "Identificador único de instalación (telemetría/diagnóstico).",
    ),
    (
        re.compile(r"\.personality_migration$"),
        "Marcador de migración de personalidad/config interna.",
    ),
    (
        re.compile(r"\.tmp/plugins"),
        "Caché temporal de plugins descargados.",
    ),
]

CONFIG_KEY_DESCRIPTIONS: dict[str, str] = {
    "model": "Modelo LLM activo.",
    "model_provider": "Proveedor del modelo (p. ej. ollama-launch, openai).",
    "approval_policy": "Cuándo pedir aprobación: untrusted | on-request | never.",
    "sandbox_mode": "Nivel de sandbox: read-only | workspace-write | danger-full-access.",
    "allow_login_shell": "Permite shell de login (mayor superficie de ataque).",
    "network_access": "Acceso a red desde el sandbox (true/false).",
    "writable_roots": "Directorios extra con permiso de escritura fuera del workspace.",
    "exclude_slash_tmp": "Excluye /tmp del sandbox de escritura.",
    "trust_level": "Confianza del proyecto: trusted permite overrides en .codex/.",
    "base_url": "Endpoint del proveedor de modelos (p. ej. Ollama).",
    "wire_api": "API wire usada para comunicación con el modelo.",
}

SANDBOX_MODES: dict[str, str] = {
    "read-only": "Solo lectura en el workspace; sin escritura ni comandos destructivos.",
    "workspace-write": "Lectura/escritura limitada al workspace y writable_roots.",
    "danger-full-access": "Acceso amplio al SO; máximo riesgo de escalada.",
}

APPROVAL_POLICIES: dict[str, str] = {
    "untrusted": "Pide aprobación para casi todas las acciones sensibles.",
    "on-request": "Pide aprobación según heurísticas y política exec.",
    "never": "No pide aprobación; ejecución autónoma (alto riesgo).",
}


def describe_file(path: Path | str) -> str:
    text = str(path).replace("\\", "/")
    for pattern, description in FILE_DESCRIPTIONS:
        if pattern.search(text):
            return description
    suffix = Path(text).suffix.lower()
    if suffix == ".toml":
        return "Fichero de configuración TOML de Codex."
    if suffix == ".json":
        return "Datos JSON de configuración o catálogo."
    if suffix == ".jsonl":
        return "Log o historial en formato JSON Lines."
    if suffix in {".sqlite", ".sqlite-wal", ".sqlite-shm"}:
        return "Base de datos SQLite del agente (estado, logs o memoria)."
    if suffix == ".md":
        return "Documentación o instrucciones en Markdown."
    return "Fichero del ecosistema Codex (revisar permisos y contenido)."


def describe_config_key(key: str) -> str:
    return CONFIG_KEY_DESCRIPTIONS.get(key, "Clave de configuración Codex.")
