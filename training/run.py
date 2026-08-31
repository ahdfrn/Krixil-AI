"""Runs one full fine-tune attempt: check readiness -> fetch dataset -> train -> export GGUF ->
register with Ollama under a temporary tag -> evaluate against the current baseline -> promote
(rename to a permanent tag) or discard (remove it) -> report the outcome. Called by scheduler.py's
periodic loop, or directly for a one-off manual run (`python run.py`).
"""

import os
import sys
from datetime import date

from client import KrixilClient
from finetune import cleanup_run_dir, new_candidate_tag, run_qlora_finetune
from ollama_ops import create_model, delete_model, rename_model

BASE_MODEL_TAG = os.environ.get("KRIXIL_BASE_MODEL_TAG", "qwen2.5:7b")


def run_once(client: KrixilClient, run_id: str | None) -> None:
    """run_id is the id of an already-existing "requested" row (a manual trigger from Settings)
    — report a clear reason if it turns out not ready. run_id=None means this was reached via the
    scheduler's own periodic readiness check with no pending manual request — if not ready, there
    is nothing to report; a self-initiated run only gets a real row once it's actually starting.
    """
    status = client.get_status()
    example_count = status["example_count"]

    if not status["ready"]:
        message = f"Not ready: {example_count}/{status['min_examples']} examples."
        print(message)
        if run_id is not None:
            client.report(run_id, "failed", detail=message)
        return

    if run_id is None:
        run_id = client.start_self_initiated_run(example_count)

    rows = client.get_dataset()
    candidate_tag = new_candidate_tag()

    try:
        print(f"Training candidate {candidate_tag} on {len(rows)} real examples...")
        modelfile_content = run_qlora_finetune(BASE_MODEL_TAG, rows, run_id)

        print(f"Registering {candidate_tag} with Ollama...")
        create_model(candidate_tag, modelfile_content)

        print("Evaluating against the current baseline...")
        eval_result = client.evaluate(candidate_tag)

        if eval_result["regression"]:
            delete_model(candidate_tag)
            client.report(
                run_id,
                "discarded",
                candidate_tag=candidate_tag,
                eval_pass_count=eval_result["pass_count"],
                eval_fail_count=eval_result["fail_count"],
                regression=True,
                detail="Regressed against the current baseline on the evaluation suite.",
            )
            print(f"Discarded {candidate_tag}: regression against baseline.")
            return

        promoted_tag = f"krixil-personalized-{date.today().isoformat()}"
        rename_model(candidate_tag, promoted_tag)
        client.report(
            run_id,
            "promoted",
            candidate_tag=candidate_tag,
            promoted_tag=promoted_tag,
            eval_pass_count=eval_result["pass_count"],
            eval_fail_count=eval_result["fail_count"],
            regression=False,
        )
        print(f"Promoted {promoted_tag} — now selectable in Krixil's model dropdown.")
    except Exception as exc:
        # Deliberately NOT cleaning up the run directory here — a failed run's checkpoints/GGUF/
        # Modelfile are exactly what's needed to debug why, and deleting them on every failure
        # made a real bug (a malformed Modelfile) unnecessarily hard to diagnose live.
        client.report(run_id, "failed", detail=str(exc))
        raise
    else:
        cleanup_run_dir(run_id)


if __name__ == "__main__":
    krixil_client = KrixilClient()
    try:
        run_once(krixil_client, run_id=None)
    except Exception as exc:  # noqa: BLE001 - top-level entry point, report and exit non-zero
        print(f"Fine-tune run failed: {exc}", file=sys.stderr)
        sys.exit(1)
