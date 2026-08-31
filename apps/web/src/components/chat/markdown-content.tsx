import { useMemo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { CodeBlock } from "@/components/chat/code-block";

function buildComponents(isStreaming: boolean): Components {
  return {
    h1: (props) => <h1 className="mt-5 mb-2 text-xl font-semibold first:mt-0" {...props} />,
    h2: (props) => <h2 className="mt-5 mb-2 text-lg font-semibold first:mt-0" {...props} />,
    h3: (props) => <h3 className="mt-4 mb-1.5 text-base font-semibold first:mt-0" {...props} />,
    p: (props) => <p className="mb-3 leading-relaxed last:mb-0" {...props} />,
    ul: (props) => <ul className="mb-3 ml-5 list-disc space-y-1 last:mb-0" {...props} />,
    ol: (props) => <ol className="mb-3 ml-5 list-decimal space-y-1 last:mb-0" {...props} />,
    li: (props) => <li className="leading-relaxed" {...props} />,
    blockquote: (props) => (
      <blockquote
        className="mb-3 border-l-2 border-primary/50 pl-3 text-muted-foreground italic last:mb-0"
        {...props}
      />
    ),
    a: (props) => (
      <a className="text-primary underline underline-offset-2 hover:no-underline" {...props} />
    ),
    hr: (props) => <hr className="my-4 border-border" {...props} />,
    strong: (props) => <strong className="font-semibold" {...props} />,
    table: (props) => (
      <div className="mb-3 overflow-x-auto rounded-md border border-border last:mb-0">
        <table className="w-full border-collapse text-sm" {...props} />
      </div>
    ),
    thead: (props) => <thead className="bg-secondary/50" {...props} />,
    th: (props) => (
      <th className="border-b border-border px-3 py-1.5 text-left font-medium" {...props} />
    ),
    td: (props) => <td className="border-b border-border px-3 py-1.5 align-top" {...props} />,
    code: ({ className, children, ...props }) => {
      const match = /language-(\w+)/.exec(className ?? "");
      const isBlock = Boolean(match);
      if (!isBlock) {
        return (
          <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[0.85em]" {...props}>
            {children}
          </code>
        );
      }
      return (
        <CodeBlock
          language={match![1]}
          code={String(children).replace(/\n$/, "")}
          isStreaming={isStreaming}
        />
      );
    },
    // react-markdown wraps block code in a <pre><code> pair — CodeBlock above already renders its
    // own container, so the outer <pre> just needs to not add its own styling.
    pre: ({ children }) => <>{children}</>,
  };
}

export function MarkdownContent({
  content,
  isStreaming = false,
}: {
  content: string;
  isStreaming?: boolean;
}) {
  // Rebuilt only when isStreaming flips (start/end of a response), not on every token — a stable
  // `components` reference matters here since react-markdown treats identity changes as "these
  // renderers changed" and re-mounts affected nodes.
  const components = useMemo(() => buildComponents(isStreaming), [isStreaming]);

  return (
    <div className="text-sm">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </Markdown>
    </div>
  );
}
