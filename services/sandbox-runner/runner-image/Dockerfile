# The image every ephemeral, network-disabled sandbox container (app/main.py's RUNNER_IMAGE) is
# spun up from — distinct from ../Dockerfile, which builds the sandbox-runner *orchestrator*
# service itself, not the containers it creates. Bare python:3.11-slim had no git/build tools/test
# runner, so `git commit` or `pytest` inside a run failed outright — this is a real toolchain for
# the coding agent's Workspace ("This Computer" mode already uses whatever's on the real machine).
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pytest

# Git refuses to commit without an identity configured — a real, silent failure mode a fresh
# sandbox would otherwise hit on the very first `git commit`. Same one used for every tenant;
# there's no per-tenant identity concept here, and this is confined to an isolated, network-
# disabled, auto-removed container each time, not a real shared machine identity.
RUN git config --system user.email "agent@krixil.local" && \
    git config --system user.name "Krixil Agent"
