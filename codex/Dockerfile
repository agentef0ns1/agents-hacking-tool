# PoC Codex CLI + Ollama remoto — laboratorio §6.1.4
FROM node:22-bookworm-slim

ARG CODEX_UID=1000
ARG CODEX_GID=1000

ENV LAB_ROOT=/opt/lab \
    CODEX_ROOT=/opt/lab/codex \
    HOME=/home/codex \
    OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    OLLAMA_MODEL=phi4-mini:latest \
    CODEX_PROFILE=ollama-launch \
    PATH=/opt/lab/codex/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        python3 \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN usermod -l codex -d /home/codex -m node \
    && groupmod -n codex node \
    && mkdir -p /home/codex \
    && chown -R codex:codex /home/codex

WORKDIR /opt/lab

COPY --chown=codex:codex scripts/ /opt/lab/scripts/
COPY --chown=codex:codex codex/ /opt/lab/codex/

RUN chmod +x /opt/lab/codex/scripts/*.sh /opt/lab/codex/docker/entrypoint.sh \
    && chmod +x /opt/lab/scripts/agent-audit-cli.py

USER codex
WORKDIR /opt/lab/codex

RUN npm install --no-fund --no-audit \
    && mkdir -p bin .codex \
    && ln -sfn ../node_modules/.bin/codex bin/codex

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/lab/codex/docker/entrypoint.sh"]
CMD []
