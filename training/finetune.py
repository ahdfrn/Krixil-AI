"""QLoRA fine-tuning via Unsloth. API verified live against Unsloth's own current documentation
and example notebooks before writing this (not assumed from possibly-stale training data) — see
docs/architecture/learning-and-memory.md Phase 3 for what was checked and why: ~5-6GB VRAM for a
7-8B model in 4-bit, native Windows support, direct GGUF export.

Uses the model's own chat template (tokenizer.apply_chat_template) rather than a hand-picked
template name — Unsloth's own docs flag an incorrect chat template as the most common cause of a
GGUF-exported model underperforming in Ollama versus in Unsloth itself, and the safest way to
avoid picking the wrong one is to not pick one at all, just use what the base instruct model
already ships with (the same template Ollama itself uses to serve that model).
"""

import os
import shutil
import uuid
from pathlib import Path

# Model-name mapping from an Ollama tag to the matching pre-quantized Unsloth/HF repo. Overridable
# via env var since these exact repo names are Unsloth's own naming choice and could change —
# verified against Unsloth's published notebooks at the time this was written, not guaranteed
# permanent.
_UNSLOTH_MODEL_MAP = {
    "qwen2.5:7b": "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    "llama3.1:8b": "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
}

WORK_DIR = Path(os.environ.get("KRIXIL_FINETUNE_WORKDIR", "./finetune_workdir"))


def _unsloth_model_name(ollama_base_tag: str) -> str:
    override = os.environ.get("KRIXIL_UNSLOTH_MODEL_OVERRIDE")
    if override:
        return override
    if ollama_base_tag not in _UNSLOTH_MODEL_MAP:
        raise ValueError(
            f"No known Unsloth model for Ollama tag '{ollama_base_tag}' — set "
            "KRIXIL_UNSLOTH_MODEL_OVERRIDE to the matching unsloth/... repo name."
        )
    return _UNSLOTH_MODEL_MAP[ollama_base_tag]


def run_qlora_finetune(base_ollama_tag: str, rows: list[dict], run_id: str) -> str:
    """Fine-tunes base_ollama_tag's matching Unsloth model on `rows` ({"prompt", "completion"}
    pairs), exports a merged GGUF, and returns the *contents* of the Ollama Modelfile Unsloth
    itself generates alongside it. Imports unsloth/torch/trl lazily — training/ is only ever
    invoked as a whole native process for this one purpose, so a module-level import cost isn't a
    concern, but keeping it inside the function makes it obvious this is the one place those
    heavy dependencies actually get loaded.
    """
    # unsloth must be imported before trl/transformers/peft to apply its optimizations (its own
    # docs and a real runtime warning caught during live verification both flag this) — importing
    # it first here, ahead of the datasets/trl imports right after, rather than relying on import
    # order elsewhere in the process.
    from unsloth import FastLanguageModel

    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    model_name = _unsloth_model_name(base_ollama_tag)
    run_dir = WORK_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    def to_text(row: dict) -> dict:
        convo = [
            {"role": "user", "content": row["prompt"]},
            {"role": "assistant", "content": row["completion"]},
        ]
        return {"text": tokenizer.apply_chat_template(convo, tokenize=False)}

    dataset = Dataset.from_list(rows).map(to_text)

    # dataset_text_field/max_length/packing live on SFTConfig, not SFTTrainer's own constructor,
    # and SFTTrainer's tokenizer param is now processing_class — verified against this installed
    # trl version's real signature (inspect.signature) after the reference notebook's older API
    # shape (tokenizer=, max_seq_length= directly on SFTTrainer) failed live with a real
    # TypeError, rather than guessing a second time.
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=2048,
            packing=False,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=5,
            num_train_epochs=1,
            learning_rate=2e-4,
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.001,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir=str(run_dir / "checkpoints"),
            report_to="none",
        ),
    )
    trainer.train()

    gguf_dir = run_dir / "gguf"
    model.save_pretrained_gguf(str(gguf_dir), tokenizer, quantization_method="q4_k_m")

    # Unsloth writes into "<given path>_gguf", not the given path itself — confirmed live (this
    # wasn't documented anywhere checked beforehand, only found by inspecting the real output of
    # a real run). It also writes its own Ollama Modelfile there, which is used as-is rather than
    # hand-rolling a minimal one — Unsloth's own docs flag an incorrect chat template as the most
    # common cause of a GGUF underperforming in Ollama, and its generated Modelfile carries the
    # correct template/parameters for this specific export, not just a bare `FROM <path>` line.
    actual_output_dir = Path(f"{gguf_dir}_gguf")
    modelfile_path = actual_output_dir / "Modelfile"
    gguf_files = list(actual_output_dir.glob("*.gguf"))
    if not modelfile_path.exists() or not gguf_files:
        raise RuntimeError(
            f"Expected a Modelfile and .gguf under {actual_output_dir}; "
            f"found .gguf files: {[f.name for f in gguf_files]}"
        )

    # Ollama's /api/create resolves a Modelfile's FROM path relative to the *server's* own
    # working directory, not this process's — Unsloth's generated FROM line is relative to where
    # it wrote the file, which won't generally match. Rewriting it to an absolute path makes this
    # correct regardless of what Ollama's own CWD happens to be. Forward slashes, not
    # Path's native backslashes — Ollama's Modelfile format is Dockerfile-derived and a raw
    # Windows backslash path in a FROM line caused a real 400 Bad Request live; Windows itself
    # accepts forward-slash paths for actual file access just fine.
    gguf_path = gguf_files[0].resolve().as_posix()
    modelfile_text = modelfile_path.read_text(encoding="utf-8")
    lines = modelfile_text.splitlines()
    lines = [f"FROM {gguf_path}" if line.strip().upper().startswith("FROM ") else line for line in lines]
    return "\n".join(lines)


def cleanup_run_dir(run_id: str) -> None:
    shutil.rmtree(WORK_DIR / run_id, ignore_errors=True)


def new_candidate_tag() -> str:
    return f"krixil-candidate-{uuid.uuid4().hex[:8]}"
