/**
 * PRD §33's CLI command surface (`kirxil ask/explain/analyze/generate/refactor/debug/test/
 * review/plan/build`) — not ten new implementations, just ten goal templates on top of the exact
 * same `runGoalOnce` path `kirxil run "<goal>"` already uses, so each one automatically gets the
 * same live transcript, the same Permission Engine pause on a HIGH-risk command, and the same
 * checkpoint-before-it-starts safety net (cli/src/checkpoint.ts) for free. What actually
 * distinguishes them is the instruction text: the read-only ones (`ask`, `explain`, `analyze`,
 * `review`, `plan`) say so explicitly, so the model doesn't reach for host.write_file/
 * host.run_command when it wasn't asked to change anything.
 */

export type VerbName =
  | "ask"
  | "explain"
  | "analyze"
  | "generate"
  | "refactor"
  | "debug"
  | "test"
  | "review"
  | "plan"
  | "build";

export interface VerbSpec {
  name: VerbName;
  argSyntax: string;
  description: string;
}

export const VERBS: VerbSpec[] = [
  { name: "ask", argSyntax: "<question>", description: "Ask a read-only question about this codebase." },
  { name: "explain", argSyntax: "<target>", description: "Explain what something in this codebase does (read-only)." },
  { name: "analyze", argSyntax: "[target]", description: "Analyze this codebase, or a target within it, for issues (read-only)." },
  { name: "generate", argSyntax: "<description>", description: "Generate new code from a description." },
  { name: "refactor", argSyntax: "<target>", description: "Refactor something without changing its behavior." },
  { name: "debug", argSyntax: "<description>", description: "Investigate and fix a bug." },
  { name: "test", argSyntax: "[target]", description: "Write or run tests." },
  {
    name: "review",
    argSyntax: "[target]",
    description: "Review the current uncommitted changes and report issues by severity (read-only).",
  },
  {
    name: "plan",
    argSyntax: "<goal>",
    description: "Investigate and produce a numbered plan for a goal — no changes made (read-only).",
  },
  {
    name: "build",
    argSyntax: "<goal>",
    description: "Plan, implement, test, and review a goal end to end in one run (PRD §20).",
  },
];

const READ_ONLY_NOTE =
  "This is read-only — investigate and report, but do not create, edit, or delete any files, " +
  "and do not run any command that changes something.";

export function buildVerbInstruction(verb: VerbName, argument: string): string {
  const arg = argument.trim();
  switch (verb) {
    case "ask":
      return `Answer this question about the code in the current directory. ${READ_ONLY_NOTE} Question: ${arg}`;
    case "explain":
      return `Explain what "${arg}" does and how it works — read whatever files are relevant first. ${READ_ONLY_NOTE}`;
    case "analyze":
      return `Analyze ${arg || "the project in this directory"} for code quality issues, structural problems, and risks. ${READ_ONLY_NOTE} Report what you find.`;
    case "generate":
      return `Generate: ${arg}. Write the file(s) needed.`;
    case "refactor":
      return `Refactor "${arg}" to improve it (clarity, structure, remove duplication) without changing its behavior. If tests already exist for it, run them afterward to confirm nothing broke.`;
    case "debug":
      return `Debug this issue: ${arg}. Investigate the real cause — read the relevant code and any error output — fix it, and verify the fix if you can (e.g. re-run whatever was failing).`;
    case "test":
      return `Write or run tests for ${arg || "the project in this directory"}. If tests already exist, run them for real and report the actual results. If not, write reasonable tests first, then run them.`;
    case "review":
      return (
        `Review the current uncommitted changes in this directory (run \`git diff\` to see them` +
        `${arg ? `, focused on ${arg}` : ""}). For each real issue you find, report it tagged ` +
        `HIGH, MEDIUM, or LOW severity, with a short explanation and the file (and line, if you ` +
        `have it). If there are no uncommitted changes, say so instead of inventing issues. ${READ_ONLY_NOTE}`
      );
    case "plan":
      return (
        `Investigate this codebase (read whatever files are relevant) and produce a plan for: ` +
        `${arg}. Format the plan as "PLAN" followed by numbered steps, each one a concrete unit ` +
        `of work — then, if you can reasonably estimate it from what you saw, roughly how many ` +
        `files and how much code it would involve. ${READ_ONLY_NOTE} Do not start implementing ` +
        `any step — this call is planning only.`
      );
    case "build":
      return (
        `Complete this goal end to end: ${arg}. Work through four real phases, in order, and say ` +
        `which phase you're in as you go: (1) Plan — briefly note the concrete steps before ` +
        `touching anything. (2) Implement — write or edit the file(s) the plan calls for, for ` +
        `real. (3) Test — run existing tests relevant to what changed if there are any, or write ` +
        `and run new ones if that's reasonable for this goal; if a test fails, fix the real cause ` +
        `and re-run it rather than reporting failure. (4) Review — look at what actually changed ` +
        `(e.g. \`git diff\`) and call out anything that looks wrong before declaring this done.`
      );
  }
}
