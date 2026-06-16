import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";

// Markdown renderer for assistant messages. Lazy-loaded (see MessageList) so
// the parser + highlighter stay out of the initial bundle. Code blocks are
// always dark (ChatGPT-style) with a hover copy button and language label.

function CodeBlock({ children, ...props }) {
  const preRef = useRef(null);
  const [copied, setCopied] = useState(false);

  // The language lands as a hljs class on the inner <code> element.
  const lang =
    (Array.isArray(children) ? children[0] : children)?.props?.className
      ?.split(" ")
      .find((c) => c.startsWith("language-"))
      ?.slice("language-".length) ?? "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(preRef.current?.innerText ?? "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — ignore */
    }
  };

  return (
    <div className="group relative my-3 overflow-hidden rounded-xl border border-zinc-800">
      <div className="flex items-center justify-between bg-zinc-800 px-3 py-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-zinc-400">
          {lang || "code"}
        </span>
        <button
          onClick={copy}
          className="rounded px-1.5 py-0.5 text-[11px] text-zinc-400 transition hover:bg-white/10 hover:text-zinc-200"
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
      <pre
        ref={preRef}
        {...props}
        className="overflow-x-auto bg-zinc-900 p-3.5 text-[13px] leading-relaxed text-zinc-100"
      >
        {children}
      </pre>
    </div>
  );
}

export default function Markdown({ children }) {
  return (
    <div className="md text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{ pre: CodeBlock }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
