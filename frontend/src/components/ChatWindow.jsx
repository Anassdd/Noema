import { useRef, useState } from "react";

import { useChatStream } from "../hooks/useChatStream.js";
import { useCommands } from "../hooks/useCommands.js";
import { usePdfUpload } from "../hooks/usePdfUpload.js";
import { useFileDrop } from "../hooks/useFileDrop.js";
import MessageList from "./MessageList.jsx";
import MessageInput from "./MessageInput.jsx";
import EmptyState from "./EmptyState.jsx";
import DocumentsPanel from "./DocumentsPanel.jsx";
import ForgetDialog from "./ForgetDialog.jsx";

// Lays out one conversation. The logic lives in hooks: useChatStream (the
// streaming turn), useCommands (slash commands), usePdfUpload + useFileDrop
// (attaching PDFs). `messages` / `setMessages` are owned by App and scoped to
// the active conversation; `memories` is the shared cross-conversation store.
export default function ChatWindow({
  messages,
  setMessages,
  memories,
  onRemember,
  onJudgeMemory,
  onForgetMemory,
  prefilterEnabled,
  memoryEnabled,
  tokenizerEnabled,
  character,
  onSetCharacter,
  documents,
  onSetDocuments,
  docsPanelOpen,
  onCloseDocsPanel,
  model,
  onUsage,
  onAutoTitle,
}) {
  const { uploading, uploadError, setUploadError, attachPdf, removeDocument } =
    usePdfUpload(onSetDocuments);

  const { runCommand, forgetCandidates, confirmForget, cancelForget } =
    useCommands({
      setMessages,
      memories,
      memoryEnabled,
      onRemember,
      onSetCharacter,
      onForgetMemory,
    });

  const { isStreaming, error, sendMessage, stop } = useChatStream({
    messages,
    setMessages,
    character,
    memories,
    documents,
    memoryEnabled,
    prefilterEnabled,
    model,
    onUsage,
    onAutoTitle,
    onJudgeMemory,
  });

  // A command is handled locally; anything else becomes a chat request.
  const send = (text) => {
    if (isStreaming) return;
    if (runCommand(text)) return;
    sendMessage(text);
  };

  const { dragActive, dropHandlers } = useFileDrop((file) => {
    const isPdf =
      file.type === "application/pdf" ||
      file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setUploadError("Please drop a PDF file.");
      return;
    }
    attachPdf(file);
  });

  // "Jump to bottom" affordance once the user scrolls up past a threshold.
  const scrollRef = useRef(null);
  const [showJump, setShowJump] = useState(false);
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setShowJump(el.scrollHeight - el.scrollTop - el.clientHeight > 300);
  };
  const jumpToBottom = () =>
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });

  const isEmpty = messages.length === 0 && documents.length === 0;

  return (
    // flex-1 + min-h-0 (NOT h-full): the header sits above this inside <main>,
    // so taking 100% of main's height would overflow it by the header's height
    // and make the whole page scroll once messages get long.
    <div className="relative flex min-h-0 flex-1 flex-col" {...dropHandlers}>
      {dragActive && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-white/80 backdrop-blur-sm dark:bg-zinc-950/80">
          <div className="rounded-2xl border-2 border-dashed border-indigo-400 bg-indigo-50/80 px-10 py-8 text-center dark:bg-indigo-950/40">
            <svg className="mx-auto h-8 w-8 text-indigo-600 dark:text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <path d="M14 2v6h6" />
            </svg>
            <p className="mt-2 text-sm font-medium text-indigo-700 dark:text-indigo-300">
              Drop your PDF to attach it
            </p>
          </div>
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        {/* pt-14 keeps content clear of the glass header floating above. */}
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="h-full overflow-y-auto pt-14"
        >
          {isEmpty ? (
            <EmptyState />
          ) : (
            <MessageList
              messages={messages}
              isStreaming={isStreaming}
              containerRef={scrollRef}
            />
          )}
        </div>
        {showJump && (
          <button
            onClick={jumpToBottom}
            aria-label="Scroll to bottom"
            className="animate-fade-in absolute bottom-4 left-1/2 grid h-9 w-9 -translate-x-1/2 place-items-center rounded-full border border-zinc-200 bg-white text-zinc-600 shadow-md transition hover:bg-zinc-50 dark:border-white/15 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12l7 7 7-7" />
            </svg>
          </button>
        )}
      </div>

      <div className="mx-auto w-full max-w-3xl px-4">
        {error && (
          <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}
        {uploadError && (
          <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            {uploadError}
          </div>
        )}
        <MessageInput
          onSend={send}
          onStop={stop}
          isStreaming={isStreaming}
          showTokenEstimate={tokenizerEnabled}
          onAttach={attachPdf}
          isUploading={uploading}
        />
        <p className="pb-3 pt-2 text-center text-xs text-zinc-400 dark:text-zinc-500">
          Answers are generated by an LLM and may be inaccurate.
        </p>
      </div>

      {docsPanelOpen && (
        <DocumentsPanel
          documents={documents}
          onAttach={attachPdf}
          onRemove={removeDocument}
          onClose={onCloseDocsPanel}
          isUploading={uploading}
        />
      )}

      {forgetCandidates.length > 0 && (
        <ForgetDialog
          facts={forgetCandidates}
          onConfirm={confirmForget}
          onCancel={cancelForget}
        />
      )}
    </div>
  );
}
