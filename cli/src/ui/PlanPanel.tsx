/**
 * Renders `kirxil plan`'s real model output in a bordered panel (Ink) — the plain-text twin of
 * runOnce.ts's own panel printing, both built from render.ts's planPanelLines so the interactive
 * REPL and `kirxil plan "<goal>"` never draw two different boxes around the same real text.
 */
import React from "react";
import { Box, Text } from "ink";
import { planPanelLines } from "../render.js";

export function PlanPanel({ planText }: { planText: string }) {
  const lines = planPanelLines(planText);
  return (
    <Box flexDirection="column">
      {lines.map((line, i) => (
        <Text key={i} color={i === 0 || i === lines.length - 1 ? "#8b7bff" : undefined} bold={i === 0 || i === lines.length - 1}>
          {line}
        </Text>
      ))}
    </Box>
  );
}
