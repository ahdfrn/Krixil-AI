import React, { useState } from "react";
import { Box, Text, useInput } from "ink";
import TextInput from "ink-text-input";

const COMMANDS = [
  { command: "/plan ", description: "Plan a task before building" },
  { command: "/model", description: "Choose Auto or NVIDIA" },
  { command: "/code ", description: "Run the coding agent with tools" },
  { command: "/new", description: "Start a fresh conversation" },
  { command: "/public ", description: "Nemotron: non-sensitive question only, asks before sending" },
  { command: "/expand", description: "Expand or collapse the last run's tool output" },
  { command: "/cwd", description: "Show the working directory" },
  { command: "/help", description: "Show commands and keyboard shortcuts" },
  { command: "/undo", description: "Review and confirm checkpoint rollback" },
  { command: "/exit", description: "Exit the interactive session" },
];

/** Selection only fills the prompt: opening a menu must never execute a command. */
export function CommandPalette({ onSelect, onClose }: {
  onSelect: (command: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const matches = COMMANDS.filter((item) =>
    `${item.command} ${item.description}`.toLowerCase().includes(query.trim().toLowerCase()),
  );
  useInput((_char, key) => {
    if (key.escape) onClose();
    if (key.upArrow) setSelected((value) => Math.max(0, value - 1));
    if (key.downArrow) setSelected((value) => Math.min(Math.max(0, matches.length - 1), value + 1));
  });
  return (
    <Box flexDirection="column" borderStyle="round" borderColor="#8b7bff" paddingX={1}>
      <Text bold color="#8b7bff">COMMAND PALETTE</Text>
      <Box>
        <Text dimColor>Search › </Text>
        <TextInput value={query} onChange={(value) => { setQuery(value); setSelected(0); }}
          onSubmit={() => { if (matches[selected]) onSelect(matches[selected].command); }} />
      </Box>
      {matches.map((item, index) => (
        <Box key={item.command} flexDirection="column" marginTop={index === 0 ? 1 : 0}>
          <Text color={index === selected ? "#8b7bff" : undefined} bold={index === selected}>
            {index === selected ? "› " : "  "}{item.command.trim()}
          </Text>
          <Text dimColor>  {item.description}</Text>
        </Box>
      ))}
      {matches.length === 0 && <Text dimColor>No matching commands. Try “plan” or “model”.</Text>}
      <Box marginTop={1}><Text dimColor>↑/↓ select · Enter insert · Esc back</Text></Box>
    </Box>
  );
}
