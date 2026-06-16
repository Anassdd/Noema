import { useState } from "react";

import Sidebar from "./components/Sidebar.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import ModelSelector from "./components/ModelSelector.jsx";
import MemoryPanel from "./components/MemoryPanel.jsx";
import CharacterPopover from "./components/CharacterPopover.jsx";
import { useConversations } from "./hooks/useConversations.js";
import { useMemory } from "./hooks/useMemory.js";
import { useModels } from "./hooks/useModels.js";
import { useSettings } from "./hooks/useSettings.js";

// App is the layout shell: it composes the domain hooks (conversations, memory,
// models, settings) and wires them into the header, sidebar, chat window, and
// the modal/panel surfaces. No domain logic lives here.
export default function App() {
  const conv = useConversations();
  const memory = useMemory();
  const { models, selectedModel, setSelectedModel, loadModels } = useModels();
  const settings = useSettings();

  // Cumulative token usage across every answer this session.
  const [sessionTokens, setSessionTokens] = useState(0);
  const trackUsage = (usage) =>
    setSessionTokens((t) => t + (usage?.total_tokens ?? 0));

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [docsPanelOpen, setDocsPanelOpen] = useState(false);
  const [memoryPanelOpen, setMemoryPanelOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null); // conv id or null
  const [confirmClearAll, setConfirmClearAll] = useState(false);

  const active = conv.active;

  return (
    <div className="flex h-full bg-white text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
      <Sidebar
        conversations={conv.conversations}
        activeId={conv.activeId}
        onOpenSettings={() => setSettingsOpen(true)}
        onNewChat={conv.newChat}
        onSelect={conv.selectConversation}
        onDelete={setPendingDelete}
        onClearHistory={() => setConfirmClearAll(true)}
      />
      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Glass header: floats over the chat so messages glide underneath. */}
        <header className="absolute inset-x-0 top-0 z-20 flex items-center justify-between border-b border-zinc-200/80 bg-white/75 px-3 py-2 backdrop-blur-md dark:border-white/10 dark:bg-zinc-950/75">
          <div className="flex min-w-0 items-center gap-1">
            <ModelSelector
              models={models}
              value={selectedModel}
              onChange={setSelectedModel}
              onReload={loadModels}
            />
            <CharacterPopover
              character={active?.character ?? ""}
              onChange={conv.setActiveCharacter}
            />
          </div>
          <div className="flex items-center gap-1">
            {sessionTokens > 0 && (
              <span
                title="Total tokens used this session (all chats)"
                className="mr-1 rounded-md bg-zinc-100 px-2 py-1 text-[11px] font-medium text-zinc-500 dark:bg-white/10 dark:text-zinc-400"
              >
                Σ {sessionTokens.toLocaleString()} tok
              </span>
            )}
            <button
              onClick={() => setMemoryPanelOpen((o) => !o)}
              aria-label="Manage memory"
              title="Manage memory"
              className="relative grid h-8 w-8 place-items-center rounded-lg text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-zinc-200"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 5a3 3 0 0 0-3 3 2.5 2.5 0 0 0-2 4 2.5 2.5 0 0 0 1.2 4.4A2.5 2.5 0 0 0 12 19a2.5 2.5 0 0 0 3.8-2.6A2.5 2.5 0 0 0 17 12a2.5 2.5 0 0 0-2-4 3 3 0 0 0-3-3z" />
                <path d="M12 5v14" />
              </svg>
              {memory.memories.length > 0 && (
                <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-[16px] place-items-center rounded-full bg-indigo-600 px-1 text-[10px] font-medium text-white">
                  {memory.memories.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setDocsPanelOpen((o) => !o)}
              aria-label="Manage PDFs"
              title="Manage PDFs"
              className="relative grid h-8 w-8 place-items-center rounded-lg text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-zinc-200"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <path d="M14 2v6h6" />
              </svg>
              {active?.documents.length > 0 && (
                <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-[16px] place-items-center rounded-full bg-indigo-600 px-1 text-[10px] font-medium text-white">
                  {active.documents.length}
                </span>
              )}
            </button>
          </div>
        </header>
        {/* key remounts the window per conversation, giving each its own
            streaming state and a clean scroll position. active is null only
            briefly while the first conversation loads from the backend. */}
        {active ? (
          <ChatWindow
            key={active.id}
          messages={active.messages}
          setMessages={conv.setActiveMessages}
          memories={memory.memories}
          onRemember={memory.addMemory}
          onJudgeMemory={memory.judgeMemory}
          onForgetMemory={memory.forgetMemories}
          prefilterEnabled={settings.prefilterEnabled}
          memoryEnabled={settings.memoryEnabled}
          tokenizerEnabled={settings.tokenizerEnabled}
          character={active.character}
          onSetCharacter={conv.setActiveCharacter}
          documents={active.documents}
          onSetDocuments={conv.setActiveDocuments}
          docsPanelOpen={docsPanelOpen}
          onCloseDocsPanel={() => setDocsPanelOpen(false)}
          model={selectedModel}
          onUsage={trackUsage}
          onAutoTitle={conv.autoTitle}
          />
        ) : (
          <div className="grid flex-1 place-items-center pt-14 text-sm text-zinc-400 dark:text-zinc-500">
            Loading…
          </div>
        )}
      </main>

      {memoryPanelOpen && (
        <MemoryPanel
          memories={memory.memories}
          memoryEnabled={settings.memoryEnabled}
          onRemove={memory.removeMemory}
          onClearAll={memory.clearMemories}
          onClose={() => setMemoryPanelOpen(false)}
        />
      )}

      {settingsOpen && (
        <SettingsModal
          memoryEnabled={settings.memoryEnabled}
          onToggleMemory={settings.toggleMemory}
          prefilterEnabled={settings.prefilterEnabled}
          onTogglePrefilter={settings.togglePrefilter}
          tokenizerEnabled={settings.tokenizerEnabled}
          onToggleTokenizer={settings.toggleTokenizer}
          darkMode={settings.darkMode}
          onToggleDarkMode={settings.toggleDarkMode}
          memoryCount={memory.memories.length}
          onClearMemory={memory.clearMemories}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      {pendingDelete !== null && (
        <ConfirmDialog
          title="Delete chat?"
          message="This conversation will be removed. This can't be undone."
          confirmLabel="Delete"
          onConfirm={() => {
            conv.deleteConversation(pendingDelete);
            setPendingDelete(null);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {confirmClearAll && (
        <ConfirmDialog
          title="Clear all conversations?"
          message="Every conversation will be permanently deleted. This can't be undone."
          confirmLabel="Clear history"
          onConfirm={() => {
            conv.clearAll();
            setConfirmClearAll(false);
          }}
          onCancel={() => setConfirmClearAll(false)}
        />
      )}
    </div>
  );
}
