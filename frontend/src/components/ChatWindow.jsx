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
import { FileIcon, ChevronDownIcon } from "./icons.jsx";

// Lays out one conversation: transcript + composer. The logic lives in hooks;
// the surrounding panel is the glass <main>, so this stays transparent.
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
  sessionTokens,
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
