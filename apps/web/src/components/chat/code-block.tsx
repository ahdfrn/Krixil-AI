"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

export function CodeBlock({
  language,
  code,
  isStreaming,
}: {
  language: string;
  code: string;
  isStreaming?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="group/code relative my-3 overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border bg-secondary/50 px-3 py-1.5">
        <span className="font-mono text-xs text-muted-foreground">{language || "text"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          {copied ? (
            <>
              <Check className="size-3" /> Copied
            </>
          ) : (
            <>
              <Copy className="size-3" /> Copy
            </>
          )}
        </button>
      </div>
      {isStreaming ? (
        // Prism's tokenizer re-parses the *entire* code block from scratch on every render —
        // fine once, but a growing block re-highlighted on every streamed token is O(n^2) work
        // over the course of a response and was freezing the tab on longer code-heavy answers
        // (real bug, caught live). Plain text while streaming; swaps to full highlighting once
        // (isStreaming flips false) when the content stops changing.
        <pre className="overflow-x-auto px-4 py-3 font-mono text-[0.8125rem] whitespace-pre-wrap">
          <code>{code}</code>
        </pre>
      ) : (
        <SyntaxHighlighter
          language={language || "text"}
          style={oneDark}
          customStyle={{
            margin: 0,
            padding: "0.75rem 1rem",
            fontSize: "0.8125rem",
            background: "transparent",
          }}
          wrapLongLines
        >
          {code}
        </SyntaxHighlighter>
      )}
    </div>
  );
}
