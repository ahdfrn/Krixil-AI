import React from "react";
import { Box, Text } from "ink";
import { existsSync, readFileSync } from "node:fs";
import { join, basename } from "node:path";

/** Real git branch of the current directory, read straight from .git/HEAD — no `git` shell-out
 * needed for this one value. "—" (not a fabricated branch name) when this isn't a git repo at
 * all, or the HEAD file doesn't parse as a symbolic ref (detached HEAD, etc.). */
function currentBranch(cwd: string): string {
  const headPath = join(cwd, ".git", "HEAD");
  if (!existsSync(headPath)) return "—";
  try {
    const content = readFileSync(headPath, "utf-8").trim();
    const match = /^ref: refs\/heads\/(.+)$/.exec(content);
    return match ? match[1]! : "detached";
  } catch {
    return "—";
  }
}

export function Banner({
  dir,
  hostRoot,
  model,
  projectName,
}: {
  dir: string;
  hostRoot: string;
  model: string;
  projectName?: string;
}) {
  const cwd = process.cwd();
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box borderStyle="round" borderColor="cyan" paddingX={2} width={46}>
        <Box flexDirection="column" alignItems="center" width="100%">
          <Text bold color="cyan">
            KIRXIL AI
          </Text>
          <Text dimColor>Autonomous Software Engineer</Text>
        </Box>
      </Box>
      <Text>
        <Text dimColor>Project: </Text>
        {projectName ?? basename(cwd)}
      </Text>
      <Text>
        <Text dimColor>Branch: </Text>
        {currentBranch(cwd)}
      </Text>
      <Text>
        <Text dimColor>Model: </Text>
        {model}
      </Text>
      <Text dimColor>
        Working in {dir} under {hostRoot}. /model to switch, /cwd for folder, /exit to quit.
      </Text>
    </Box>
  );
}
