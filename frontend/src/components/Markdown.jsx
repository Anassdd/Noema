import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

// Markdown renderer for assistant messages. Lazy-loaded (see MessageList) so
// the parser + highlighter stay out of the initial bundle. Code blocks follow
// the theme (light card in light mode, dark in dark mode); token colors come
// from the theme-aware .hljs rules in index.css.

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
    <div
      className="group relative my-3 overflow-hidden rounded-xl border"
      style={{ borderColor: "var(--code-border)" }}
    >
      <div
        className="flex items-center justify-between px-3.5 py-2"
        style={{ background: "var(--code-header-bg)", borderBottom: "1px solid var(--code-border)" }}
      >
        <span className="font-mono text-[11px] uppercase tracking-wide" style={{ color: "var(--text-faint)" }}>
          {lang || "code"}
        </span>
        <button
          onClick={copy}
          className="rounded px-1.5 py-0.5 font-mono text-[11px] transition hover:bg-[var(--row-hover)]"
          style={{ color: "var(--text-faint)" }}
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
      <pre
        ref={preRef}
        {...props}
        className="overflow-x-auto p-3.5 text-[13px] leading-relaxed"
        style={{ background: "var(--code-bg)", color: "var(--code-text)" }}
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
