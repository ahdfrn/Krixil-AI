import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, basename } from "node:path";
import type { KrixilApi } from "../api.js";

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

interface TopLevelCounts {
  files: number;
  dirs: number;
}

/** A real, cheap top-level count — not a fabricated "12,482 files indexed" implying an AST/
 * dependency scan that doesn't exist anywhere in Krixil. Just what's actually sitting in this one
 * directory, the same thing `host.list_files`/`ls` would show. null (not 0) on any read failure
 * (permissions, path gone) so the banner honestly omits the line instead of claiming "0 files". */
function topLevelCounts(cwd: string): TopLevelCounts | null {
  try {
    const entries = readdirSync(cwd, { withFileTypes: true });
    let files = 0;
    let dirs = 0;
    for (const entry of entries) {
      if (entry.isDirectory()) dirs++;
      else if (entry.isFile()) files++;
    }
    return { files, dirs };
  } catch {
    return null;
  }
}

export function Banner({
  api,
  dir,
  hostRoot,
  model,
  projectName,
}: {
  api: KrixilApi;
  dir: string;
  hostRoot: string;
  model: string;
  projectName?: string;
}) {
  const cwd = process.cwd();
  const counts = topLevelCounts(cwd);
  // null = still checking, not yet "offline" — a real probe against the real backend
  // (api.listModels(), the same authenticated call `kirxil models` makes), not a hardcoded
  // "● ONLINE" with nothing behind it.
  const [online, setOnline] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    api
      .listModels()
      .then(() => {
        if (!cancelled) setOnline(true);
      })
      .catch(() => {
        if (!cancelled) setOnline(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box borderStyle="round" borderColor="cyan" paddingX={2} width={46} justifyContent="space-between">
        <Text bold color="cyan">
          KIRXIL AI
        </Text>
        <Text color={online === null ? "yellow" : online ? "green" : "red"}>
          {online === null ? "○ checking" : online ? "● online" : "○ offline"}
        </Text>
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
      {counts && (
        <Text dimColor>
          {counts.files} file{counts.files === 1 ? "" : "s"}, {counts.dirs} folder{counts.dirs === 1 ? "" : "s"} here
        </Text>
      )}
      <Text dimColor>
        Working in {dir} under {hostRoot}. /model to switch, /cwd for folder, /exit to quit.
      </Text>
    </Box>
  );
}
