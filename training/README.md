# training/ — autonomous fine-tuning

Runs **natively on Windows**, not in Docker — it needs real CUDA/GPU access the same way Ollama
itself does, and a Linux container can't reach that. It talks to the running `api` service over
plain HTTP (same auth as any other client), and to the local Ollama instance directly.

See [`docs/architecture/learning-and-memory.md`](../docs/architecture/learning-and-memory.md)
(Phase 3) for the full design and why it's built this way.

## Setup

```powershell
cd training
python -m venv .venv
.venv\Scripts\activate

# Plain pip — pulls in a CUDA-enabled torch build automatically for the common case. (Not the
# irm .../install.ps1 script: that installs a separate desktop IDE app, "Unsloth Studio", with its
# own managed environment — checked its actual contents before deciding against it.)
pip install unsloth
pip install -r requirements.txt

Copy-Item .env.example .env
# edit .env: set KRIXIL_TENANT_SLUG / KRIXIL_EMAIL / KRIXIL_PASSWORD to a real Krixil login
```

## Running

**One-off manual run** (fetches the dataset, checks readiness, trains if ready, exits):

```powershell
python run.py
```

**The actual "runs on its own" loop** — leave this running (a terminal window, or registered as a
Windows Scheduled Task running `python scheduler.py` at logon):

```powershell
python scheduler.py
```

It checks the api service periodically (`KRIXIL_FINETUNE_POLL_SECONDS`, default hourly) for either
a pending manual "Run now" request from Settings → Fine-tuning, or real data readiness (enough
real conversation history — see the api's `GET /finetune/status`). Below the readiness threshold,
it does nothing except log that it's waiting — this is what makes the autonomous loop safe to
leave running even when there isn't enough data yet.

## What a real run does

1. Fetch the dataset (`GET /finetune/dataset`) — real conversation turns, already filtered by the
   `memory_enabled` privacy toggle and a minimum-length quality filter on the api side.
2. QLoRA fine-tune the configured base model (`KRIXIL_BASE_MODEL_TAG`) via Unsloth.
3. Export a merged GGUF and register it with Ollama under a temporary `krixil-candidate-*` tag —
   never visible as a selectable model yet.
4. Evaluate the candidate against the current baseline using Krixil's existing evaluation harness
   (`POST /finetune/evaluate`).
5. **Regressed → discarded** (`ollama rm`'d immediately, never shown as an option).
   **Did not regress → promoted** (renamed to a permanent `krixil-personalized-<date>` tag, which
   then appears as a real, additional choice in Krixil's model dropdown — the base models are
   never replaced or hidden).
6. Reports the outcome back (`POST /finetune/report`), visible in Settings → Fine-tuning.

## A known trade-off, not a bug

A training run and live Ollama chat share the same GPU — chat will be noticeably slower while a
fine-tune is running. Reasonable for a personal, single-user tool; not addressed with a
time-of-day scheduling window in this version.
