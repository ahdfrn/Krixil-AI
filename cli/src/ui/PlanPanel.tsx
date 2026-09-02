/**
 * Wraps real plan output in an Ink border that adapts to the available terminal width.
 * Plain non-interactive output retains its separate text renderer.
 */
import React from "react";
import { Box, Text } from "ink";

export function PlanPanel({ planText }: { planText: string }) {
  return (
    <Box flexDirection="column" width="100%" borderStyle="round" borderColor="#8b7bff" paddingX={1}>
      <Text bold color="#8b7bff">ENGINEERING PLAN</Text>
      <Text dimColor>Review the proposal before starting a build.</Text>
      <Box marginTop={1}><Text>{planText}</Text></Box>
    </Box>
  );
}
