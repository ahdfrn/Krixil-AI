/**
 * A persistent context bar for the interactive REPL — real tool-call count, the real self-healing
 * pass/fail sequence, and real working-tree change stats for the current run, not fabricated
 * "context usage" or "tokens" figures Krixil doesn't track. Change stats reuse checkpoint.ts's own
 * git plumbing (workingTreeChangeSummary) so this and `kirxil undo` never disagree about what
 * "changed" means.
 */
import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import { workingTreeChangeSummary, type ChangeSummary } from "../checkpoint.js";
import { testOutcomesLabel, type TestOutcome } from "../render.js";

const POLL_MS = 2000;

export function StatusBar({ toolCalls, testOutcomes }: { toolCalls: number; testOutcomes: TestOutcome[] }) {
  const [changes, setChanges] = useState<ChangeSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      workingTreeChangeSummary(process.cwd())
        .then((c) => {
          if (!cancelled) setChanges(c);
        })
        .catch(() => {
          /* best-effort — leave the last known value rather than showing an error here */
        });
    };
    poll();
    const interval = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const parts = [`${toolCalls} tool call${toolCalls === 1 ? "" : "s"}`];
  const testsLabel = testOutcomesLabel(testOutcomes);
  if (testsLabel) parts.push(`tests ${testsLabel}`);
  if (changes && (changes.insertions > 0 || changes.deletions > 0)) {
    parts.push(`+${changes.insertions}/-${changes.deletions}`);
  }

  return (
    <Box borderStyle="round" borderColor="gray" paddingX={1} width="100%" justifyContent="space-between">
      <Text dimColor>{parts.join(" · ")}</Text>
      <Text dimColor>/help /model /cwd /expand /undo /exit</Text>
    </Box>
  );
}
