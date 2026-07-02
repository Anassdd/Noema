import { useRef } from "react";

import { estimateTokens } from "../lib/tokens.js";
import { DOC_STUFF_MAX_TOKENS, documentsFit } from "../lib/systemPrompt.js";

// Right-side drawer to manage the conversation's attached PDFs: list them,
// remove individual ones, or add another. Click the backdrop or × to close.
export default function DocumentsPanel({
  documents,
  onAttach,
  onRemove,
  onClose,
  isUploading,
}) {
  const fileRef = useRef(null);
  const totalTokens = documents.reduce(
    (sum, d) => sum + estimateTokens(d.text),
    0,
  );
  const fits = documentsFit(documents);

  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onAttach?.(file);
    e.target.value = "";
  };

  return (
    <div
      className="animate-fade-in fixed inset-0 z-40 flex justify-end bg-black/30"
      onClick={onClose}
    >
      <div
        className="animate-slide-in-right flex h-full w-80 flex-col bg-white shadow-xl dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-white/10">
          <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
            Attached PDFs{documents.length > 0 ? ` (${documents.length})` : ""}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close panel"
            className="grid h-7 w-7 place-items-center rounded-lg text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-white/10 dark:hover:text-zinc-200"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {documents.length === 0 ? (
            <p className="mt-8 text-center text-sm text-zinc-400">
              No PDFs attached yet.
            </p>
          ) : (
            documents.map((d) => (
              <div
                key={d.id}
                className="flex items-start gap-2 rounded-lg border border-zinc-200 p-2.5 dark:border-white/10"
              >
                <FileIcon className="mt-0.5 h-4 w-4 shrink-0 text-zinc-600 dark:text-zinc-300" />
                <div className="min-w-0 flex-1">
                  <div
                    className="truncate text-sm font-medium text-zinc-700 dark:text-zinc-200"
                    title={d.filename}
                  >
                    {d.filename}
                  </div>
                  <div className="text-xs text-zinc-400">
                    {d.pages} {d.pages === 1 ? "page" : "pages"} · ~
                    {estimateTokens(d.text).toLocaleString()} tokens
                  </div>
                </div>
                <button
                  onClick={() => onRemove(d.id)}
                  aria-label="Remove PDF"
                  className="shrink-0 rounded-md p-1 text-zinc-400 transition hover:bg-red-50 hover:text-red-500"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>

        <div className="space-y-2 border-t border-zinc-200 p-3 dark:border-white/10">
          {documents.length > 0 &&
            (fits ? (
              <p className="text-center text-xs text-zinc-400">
                ~{totalTokens.toLocaleString()} tokens added to every message
              </p>
            ) : (
              <p className="text-center text-xs text-amber-600 dark:text-amber-400">
                ~{totalTokens.toLocaleString()} tokens — over the ~
                {DOC_STUFF_MAX_TOKENS.toLocaleString()}-token limit, so these aren’t sent to the
                model. Add them on the Graph page to index them.
              </p>
            ))}
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={onFileChange}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={isUploading}
            className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isUploading ? "Uploading…" : "Add PDF"}
          </button>
        </div>
      </div>
    </div>
  );
}

function FileIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}
