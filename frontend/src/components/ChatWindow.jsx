import { useEffect, useRef, useState } from "react";

import { useChatStream } from "../hooks/useChatStream.js";
import { useCommands } from "../hooks/useCommands.js";
import { usePdfUpload } from "../hooks/usePdfUpload.js";
import { useFileDrop } from "../hooks/useFileDrop.js";
import MessageList from "./MessageList.jsx";
import MessageInput from "./MessageInput.jsx";
import EmptyState from "./EmptyState.jsx";
import DocumentsPanel from "./DocumentsPanel.jsx";
import ForgetDialog from "./ForgetDialog.jsx";
import { BrainIcon, ChevronDownIcon, CloseIcon, FileIcon } from "./icons.jsx";

// Lays out one conversation: transcript + composer. The logic lives in hooks;
// the surrounding panel is the glass <main>, so this stays transparent.
export default function ChatWindow({
  messages,
  setMessages,
  memories,
  memoryContext,
  memoryReady,
  onRemember,
  onJudgeMemory,
  onForgetMemory,
  prefilterEnabled,
  memoryEnabled,
  expertEnabled,
  selectedMemory,
  onSelectMemory,
  retrievalMode,
  onSelectRetrieval,
  tokenizerEnabled,
  character,
  onSetCharacter,
  documents,
  onSetDocuments,
  docsPanelOpen,
  onCloseDocsPanel,
  model,
  sessionTokens,
  onUsage,
  onAutoTitle,
}) {
  const { uploading, uploadError, setUploadError, attachPdf, removeDocument } =
    usePdfUpload(onSetDocuments);

  const { runCommand, forgetCandidates, confirmForget, cancelForget } =
    useCommands({
      setMessages,
      messages,
      memories,
      memoryEnabled,
      onRemember,
      onSetCharacter,
      onForgetMemory,
      selectedMemory,
      expertEnabled,
    });

  // Memory-judge results show as a transient notification above the composer,
  // not inside the transcript.
  const [memoryNote, setMemoryNote] = useState("");
  const noteTimer = useRef(null);
  const showMemoryNote = (text) => {
    setMemoryNote(text);
    clearTimeout(noteTimer.current);
    noteTimer.current = setTimeout(() => setMemoryNote(""), 6000);
  };
  useEffect(() => () => clearTimeout(noteTimer.current), []);

  const { isStreaming, error, sendMessage, stop } = useChatStream({
    messages,
    setMessages,
    character,
    memoryContext,
    memoryReady,
    documents,
    memoryEnabled,
    prefilterEnabled,
    expertEnabled,
    memory: selectedMemory,
    retrieval: retrievalMode,
    model,
    onUsage,
    onAutoTitle,
    onJudgeMemory,
    onMemoryNote: showMemoryNote,
  });

  const send = (text) => {
    if (isStreaming) return;
    // Sending always rejoins the conversation's tail, wherever you'd scrolled.
    setTimeout(() => {
      scrollRef.current?.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }, 60);
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

  const scrollRef = useRef(null);
  const [showJump, setShowJump] = useState(false);
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setShowJump(el.scrollHeight - el.scrollTop - el.clientHeight > 300);
  };
  const jumpToBottom = () =>
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });

  const isEmpty = messages.length === 0 && documents.length === 0;

  return (
    <div className="relative flex min-h-0 flex-1 flex-col" {...dropHandlers}>
      {dragActive && (
        <div
          className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center backdrop-blur-md"
          style={{ background: "var(--panel-bg)" }}
        >
          <div
            className="rounded-2xl border-2 border-dashed px-12 py-10 text-center"
            style={{ borderColor: "var(--accent)", background: "var(--accent-soft)", color: "var(--accent)" }}
          >
            <div className="flex justify-center">
              <FileIcon size={30} />
            </div>
            <p className="mt-2 text-sm font-medium">Drop your PDF to attach it</p>
          </div>
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} onScroll={onScroll} className="h-full overflow-y-auto">
          {isEmpty ? (
            <EmptyState />
          ) : (
            <MessageList messages={messages} isStreaming={isStreaming} containerRef={scrollRef} />
          )}
        </div>
        {showJump && (
          <button
            onClick={jumpToBottom}
            aria-label="Scroll to bottom"
            className="animate-fade-in absolute bottom-4 left-1/2 grid h-9 w-9 -translate-x-1/2 place-items-center rounded-full border"
            style={{ background: "var(--user-bubble)", borderColor: "var(--border)", color: "var(--text-soft)" }}
          >
            <ChevronDownIcon size={16} sw={2.2} />
          </button>
        )}
      </div>

      <div className="flex-shrink-0 px-7 pb-4 pt-2.5">
        {memoryNote && (
          <div className="mx-auto mb-2 w-full max-w-[720px]">
            <div
              className="animate-fade-in flex items-start gap-2 rounded-lg border px-3 py-2 text-[12.5px]"
              style={{
                borderColor: "var(--accent-border)",
                background: "var(--accent-soft)",
                color: "var(--text-soft)",
              }}
            >
              <span className="mt-0.5 shrink-0" style={{ color: "var(--accent)" }}>
                <BrainIcon size={14} sw={1.8} />
              </span>
              <span className="min-w-0 flex-1">{memoryNote}</span>
              <button
                onClick={() => setMemoryNote("")}
                aria-label="Dismiss"
                className="shrink-0 rounded p-0.5 transition hover:opacity-70"
                style={{ color: "var(--text-faint)" }}
              >
                <CloseIcon size={13} />
              </button>
            </div>
          </div>
        )}
        {(error || uploadError) && (
          <div className="mx-auto mb-2 w-full max-w-[720px]">
            <div
              className="rounded-lg border px-3 py-2 text-sm"
              style={{ borderColor: "var(--danger)", color: "var(--danger)", background: "var(--accent-soft)" }}
            >
              {error || uploadError}
            </div>
          </div>
        )}
        <MessageInput
          onSend={send}
          onStop={stop}
          isStreaming={isStreaming}
          showTokenEstimate={tokenizerEnabled}
          onAttach={attachPdf}
          isUploading={uploading}
          model={model}
          sessionTokens={sessionTokens}
          memory={selectedMemory}
          onSelectMemory={onSelectMemory}
          retrieval={retrievalMode}
          onSelectRetrieval={onSelectRetrieval}
          expertEnabled={expertEnabled}
        />
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
        <ForgetDialog facts={forgetCandidates} onConfirm={confirmForget} onCancel={cancelForget} />
      )}
    </div>
  );
}
