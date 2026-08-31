"""Local Ollama model management via its CLI, not the raw HTTP API.

Checked the raw HTTP `/api/create` contract live against Ollama's current docs after a real 400
error — its current form needs the GGUF pre-uploaded as a content-addressed blob (SHA256 digest)
before `/api/create` will accept it, a much more involved flow than the CLI-style `FROM <path>`
Modelfile Unsloth itself generates and explicitly recommends running via `ollama create <name> -f
<path>`. Since training/ runs natively on the same machine Ollama does, shelling out to the real
CLI is simpler and more robust than reimplementing blob upload by hand — it's the same path
Unsloth's own printed instructions point at.
"""

import os
import subprocess
import tempfile
from pathlib import Path

OLLAMA_EXE = os.environ.get(
    "KRIXIL_OLLAMA_EXE",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"),
)


def _run(*args: str, timeout: float) -> None:
    result = subprocess.run(
        [OLLAMA_EXE, *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"`ollama {' '.join(args)}` failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def create_model(tag: str, modelfile_content: str) -> None:
    """Registers a GGUF file as a new Ollama model from a complete Modelfile's contents — the one
    Unsloth itself generates alongside its GGUF export (finetune.py's run_qlora_finetune reads and
    returns it, with its FROM line rewritten to an absolute path), not a hand-rolled minimal one.
    Matches the warning in Unsloth's own docs that an incorrect chat template is the most common
    cause of a GGUF underperforming in Ollama versus in Unsloth itself — using their own generated
    Modelfile carries whatever template/parameters they determined were correct for this export.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".Modelfile", delete=False, encoding="utf-8"
    ) as f:
        f.write(modelfile_content)
        modelfile_path = f.name
    try:
        _run("create", tag, "-f", modelfile_path, timeout=600.0)
    finally:
        Path(modelfile_path).unlink(missing_ok=True)


def rename_model(source_tag: str, destination_tag: str) -> None:
    _run("cp", source_tag, destination_tag, timeout=60.0)
    delete_model(source_tag)


def delete_model(tag: str) -> None:
    try:
        _run("rm", tag, timeout=60.0)
    except RuntimeError as exc:
        if "not found" not in str(exc).lower():
            raise
