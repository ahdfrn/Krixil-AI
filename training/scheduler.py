"""The actual "mandiri" (autonomous) loop. Runs as a long-lived native Windows process — left
running in a terminal, or registered as a Windows Scheduled Task (see training/README.md) — that
periodically polls the api service for either a pending manual "Run now" request (from Settings)
or real data readiness, and runs the fine-tuning pipeline (run.py) in-process when either is true.

This deliberately lives here, not inside the api container's own lifespan: a real fine-tune needs
CUDA/GPU access, and a Linux Docker container cannot spawn a process with the Windows host's GPU
access — the same reason Ollama itself runs natively rather than inside Docker. So the direction
is reversed: this native process polls the containerized api over HTTP, rather than the api
container trying to launch a native process it fundamentally cannot reach.
"""

import os
import time

from client import KrixilClient
from run import run_once

POLL_INTERVAL_SECONDS = int(os.environ.get("KRIXIL_FINETUNE_POLL_SECONDS", str(60 * 60)))


def find_pending_manual_request(status: dict) -> str | None:
    for run in status["runs"]:
        if run["status"] == "requested":
            return run["id"]
    return None


def poll_once(client: KrixilClient) -> None:
    status = client.get_status()
    pending_run_id = find_pending_manual_request(status)

    if pending_run_id is not None:
        print(f"Picking up manually-requested run {pending_run_id}.")
        run_once(client, run_id=pending_run_id)
        return

    if status["ready"]:
        print("Data readiness threshold met — starting a self-initiated run.")
        run_once(client, run_id=None)
        return

    print(
        f"Not ready ({status['example_count']}/{status['min_examples']} examples), "
        "no pending request. Waiting for the next check."
    )


if __name__ == "__main__":
    krixil_client = KrixilClient()
    print(f"Fine-tune scheduler started — checking every {POLL_INTERVAL_SECONDS}s.")
    while True:
        try:
            poll_once(krixil_client)
        except Exception as exc:  # noqa: BLE001 - keep the loop alive across a bad cycle
            print(f"Poll cycle failed: {exc}")
        time.sleep(POLL_INTERVAL_SECONDS)
