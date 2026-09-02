import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, basename } from "node:path";
import figlet from "figlet";
import type { KrixilApi } from "../api.js";
import { VERSION } from "../version.js";

// Rendered once at module load, not per-render — figlet's own text layout is pure and static for
// a fixed string/font, no reason to redo the work on every keystroke.
const WORDMARK_LINES = figlet.textSync("KIRXIL", { font: "ANSI Shadow" }).replace(/\n+$/, "").split("\n");

// Krixil's own established brand accent (indigo → violet) — the same pair used in the web app's
// design tokens and the CLI setup guide artifact, not a generic terminal color picked for this
// one component. Interpolated across the wordmark's lines for a vertical gradient.
const GRADIENT_FROM: [number, number, number] = [0x5b, 0x4c, 0xf0]; // #5b4cf0
const GRADIENT_TO: [number, number, number] = [0x8b, 0x7b, 0xff]; // #8b7bff

function lerpHex(from: [number, number, number], to: [number, number, number], t: number): string {
  const [fr, fg, fb] = from;
  const [tr, tg, tb] = to;
  const channel = (a: number, b: number) => Math.round(a + (b - a) * t).toString(16).padStart(2, "0");
  return `#${channel(fr, tr)}${channel(fg, tg)}${channel(fb, tb)}`;
}

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
      <Box flexDirection="column">
        {WORDMARK_LINES.map((line, i) => (
          <Text key={i} bold color={lerpHex(GRADIENT_FROM, GRADIENT_TO, WORDMARK_LINES.length <= 1 ? 0 : i / (WORDMARK_LINES.length - 1))}>
            {line}
          </Text>
        ))}
      </Box>
      <Box justifyContent="space-between" width={39}>
        <Text dimColor>v{VERSION}</Text>
        <Text color={online === null ? "yellow" : online ? "green" : "red"}>
          {online === null ? "○ checking" : online ? "● online" : "○ offline"}
        </Text>
      </Box>
      <Box height={1} />
      <Text>
        <Text dimColor>Project </Text>
        {projectName ?? basename(cwd)}
      </Text>
      <Text>
        <Text dimColor>Branch  </Text>
        {currentBranch(cwd)}
      </Text>
      <Text>
        <Text dimColor>Model   </Text>
        {model}
      </Text>
      {counts && (
        <Text dimColor>
          {counts.files} file{counts.files === 1 ? "" : "s"}, {counts.dirs} folder{counts.dirs === 1 ? "" : "s"} here
        </Text>
      )}
      <Box height={1} />
      <Text dimColor>
        Working in {dir} under {hostRoot}. /help for commands, /exit to quit.
      </Text>
    </Box>
  );
}
