/**
 * Shared readline prompt — used by `kirxil login` (index.ts) and by the plain, non-Ink approval
 * flow (runOnce.ts) for `kirxil run "<goal>"`. Pulled out of index.ts so both can use the exact
 * same masked-password/plain-question logic instead of two copies drifting apart.
 */

import readline from "node:readline";

export function prompt(question: string, hidden = false): Promise<string> {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    if (hidden) {
      // readline has no built-in masked input — muting output writes while this question is
      // active is the standard workaround (same trade-off most lightweight CLIs make rather than
      // pulling in a dedicated password-prompt dependency for one field).
      const rlAny = rl as unknown as { _writeToOutput: (s: string) => void };
      const originalWrite = rlAny._writeToOutput.bind(rl);
      rlAny._writeToOutput = (stringToWrite: string) => {
        if (stringToWrite.includes(question)) originalWrite(stringToWrite);
      };
    }
    rl.question(question, (answer) => {
      rl.close();
      if (hidden) process.stdout.write("\n");
      resolve(answer.trim());
    });
  });
}

export async function confirm(question: string): Promise<boolean> {
  const answer = await prompt(`${question} [y/N] `);
  const normalized = answer.toLowerCase();
  return normalized === "y" || normalized === "yes";
}
