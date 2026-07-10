import { useState } from "react";

import Sidebar from "./components/Sidebar.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import ModelSelector from "./components/ModelSelector.jsx";
import MemoryPanel from "./components/MemoryPanel.jsx";
import {
  PanelIcon,
  BrainIcon,
  FileIcon,
  SunIcon,
  MoonIcon,
  GraphIcon,
  BenchIcon,
} from "./components/icons.jsx";
import { useConversations } from "./hooks/useConversations.js";
import { useMemory } from "./hooks/useMemory.js";
import { useModels } from "./hooks/useModels.js";
import { useSettings } from "./hooks/useSettings.js";

// A header icon button in the theme style: outlined, accent-filled when active,
// with an optional count badge.
function HeaderButton({ icon, label, active, count, onClick }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="relative grid h-8 w-8 place-items-center rounded-[9px] border"
      style={{
        borderColor: active ? "var(--accent-border)" : "var(--border)",
        background: active ? "var(--accent-soft)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-soft)",
      }}
    >
      {icon}
      {count > 0 && (
        <span
          className="absolute -right-1 -top-1 grid h-4 min-w-[16px] place-items-center rounded-full px-1 font-mono text-[9px] font-medium text-white"
          style={{ background: "var(--accent)" }}
        >
          {count}
        </span>
      )}
    </button>
  );
}

export default function App() {
  const conv = useConversations();
  const memory = useMemory();
  const { models, selectedModel, setSelectedModel, loadModels } = useModels();
  const settings = useSettings();

  const [sessionTokens, setSessionTokens] = useState(0);
  const trackUsage = (usage) =>
    setSessionTokens((t) => t + (usage?.total_tokens ?? 0));

  // Which saved memory snapshot the expert answers from (null = live memory).
  const [selectedMemory, setSelectedMemory] = useState(null);
  // Which store the expert retrieves from: "hybrid" (default) | "rag" | "graph" | "lightrag".
  const [retrievalMode, setRetrievalMode] = useState("hybrid");

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [docsPanelOpen, setDocsPanelOpen] = useState(false);
  const [memoryPanelOpen, setMemoryPanelOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [confirmClearAll, setConfirmClearAll] = useState(false);

  const active = conv.active;

  return (
    <div className="app-bg flex h-full w-full overflow-hidden">
      <Sidebar
        open={sidebarOpen}
        conversations={conv.conversations}
        activeId={conv.activeId}
        onNewChat={conv.newChat}
        onSelect={conv.selectConversation}
        onDelete={setPendingDelete}
        onClearHistory={() => setConfirmClearAll(true)}
        onOpenSettings={() => setSettingsOpen(true)}
        onCollapse={() => setSidebarOpen(false)}
      />

      <main
        className="glass-panel relative flex min-w-0 flex-1 flex-col"
        style={{ color: "var(--text)" }}
      >
        <header
          className="flex h-14 flex-shrink-0 items-center gap-3 border-b px-5"
          style={{ borderColor: "var(--border-soft)" }}
        >
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Show conversations"
              title="Show conversations"
              className="grid h-8 w-8 place-items-center rounded-[9px]"
              style={{ color: "var(--text-soft)" }}
            >
              <PanelIcon size={17} />
            </button>
          )}
          <HeaderButton
            icon={<GraphIcon size={17} sw={1.7} />}
            label="Graph memory"
            onClick={() =>
              window.open(`${window.location.origin}/?view=graph`, "_blank", "noopener")
            }
          />
          <HeaderButton
            icon={<BenchIcon size={17} sw={1.7} />}
            label="Bench — compare memory methods"
            onClick={() =>
              window.open(`${window.location.origin}/?view=bench`, "_blank", "noopener")
            }
          />
          <div
            className="font-serif truncate text-[17px]"
            style={{ fontWeight: "var(--title-weight)", color: "var(--text)" }}
          >
            {active?.title || "New chat"}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <ModelSelector
              models={models}
              value={selectedModel}
              onChange={setSelectedModel}
              onReload={loadModels}
            />
            <HeaderButton
              icon={settings.darkMode ? <SunIcon size={16} /> : <MoonIcon size={16} />}
              label={settings.darkMode ? "Light mode" : "Dark mode"}
              onClick={settings.toggleDarkMode}
            />
            <HeaderButton
              icon={<BrainIcon size={17} sw={1.6} />}
              label="Manage memory"
              active={memoryPanelOpen}
              count={memory.memories.length}
              onClick={() => setMemoryPanelOpen((o) => !o)}
            />
            <HeaderButton
              icon={<FileIcon size={16} />}
              label="Manage PDFs"
              active={docsPanelOpen}
              count={active?.documents.length ?? 0}
              onClick={() => setDocsPanelOpen((o) => !o)}
            />
          </div>
        </header>

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
            expertEnabled={settings.expertEnabled}
            selectedMemory={selectedMemory}
            onSelectMemory={setSelectedMemory}
            retrievalMode={retrievalMode}
            onSelectRetrieval={setRetrievalMode}
            tokenizerEnabled={settings.tokenizerEnabled}
            character={active.character}
            onSetCharacter={conv.setActiveCharacter}
            documents={active.documents}
            onSetDocuments={conv.setActiveDocuments}
            docsPanelOpen={docsPanelOpen}
            onCloseDocsPanel={() => setDocsPanelOpen(false)}
            model={selectedModel}
            sessionTokens={sessionTokens}
            onUsage={trackUsage}
            onAutoTitle={conv.autoTitle}
          />
        ) : (
          <div
            className="grid flex-1 place-items-center text-sm"
            style={{ color: "var(--text-faint)" }}
          >
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
          expertEnabled={settings.expertEnabled}
          onToggleExpert={settings.toggleExpert}
          prefilterEnabled={settings.prefilterEnabled}
          onTogglePrefilter={settings.togglePrefilter}
          tokenizerEnabled={settings.tokenizerEnabled}
          onToggleTokenizer={settings.toggleTokenizer}
          darkMode={settings.darkMode}
          onToggleDarkMode={settings.toggleDarkMode}
          themeFamily={settings.themeFamily}
          onApplyTheme={settings.setThemeFamily}
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
