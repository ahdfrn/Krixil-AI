import { apiFetch } from "@/lib/api/client";

export interface FinetuneRun {
  id: string;
  status: "requested" | "running" | "promoted" | "discarded" | "failed";
  example_count: number;
  candidate_tag: string | null;
  promoted_tag: string | null;
  eval_pass_count: number | null;
  eval_fail_count: number | null;
  regression: boolean | null;
  detail: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface FinetuneStatus {
  example_count: number;
  min_examples: number;
  ready: boolean;
  runs: FinetuneRun[];
}

export async function getFinetuneStatus(): Promise<FinetuneStatus> {
  return apiFetch<FinetuneStatus>("/finetune/status");
}

export async function triggerFinetuneRun(): Promise<FinetuneRun> {
  return apiFetch<FinetuneRun>("/finetune/run", { method: "POST" });
}
