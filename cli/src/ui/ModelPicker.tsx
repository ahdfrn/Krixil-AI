import React, { useState } from "react";
import { Box, Text, useInput } from "ink";

export type ModelChoice = "auto" | "nvidia";

export function ModelPicker({ current, onSelect, onClose }: {
  current: string;
  onSelect: (model: ModelChoice) => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(current === "nvidia" ? 1 : 0);
  useInput((_char, key) => {
    if (key.escape) onClose();
    if (key.upArrow || key.downArrow) setSelected((value) => 1 - value);
    if (key.return) onSelect(selected === 0 ? "auto" : "nvidia");
  });
  return (
    <Box flexDirection="column" borderStyle="round" borderColor="#8b7bff" paddingX={1}>
      <Text bold>SELECT MODEL</Text>
      <Text color={selected === 0 ? "#8b7bff" : undefined} bold={selected === 0}>
        {selected === 0 ? "›" : " "} Auto {current === "auto" ? "✓" : ""}
      </Text>
      <Text dimColor>  Chat + Code · configured fallback chain</Text>
      <Text color={selected === 1 ? "#8b7bff" : undefined} bold={selected === 1}>
        {selected === 1 ? "›" : " "} NVIDIA {current === "nvidia" ? "✓" : ""}
      </Text>
      <Text dimColor>  Nemotron · public chat only · confirmation before sending</Text>
      <Text dimColor>↑/↓ select · Enter choose · Esc cancel</Text>
    </Box>
  );
}
