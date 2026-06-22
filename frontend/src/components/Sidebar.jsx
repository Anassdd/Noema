import {
  Icon,
  PanelIcon,
  NewChatIcon,
  TrashIcon,
  GearIcon,
} from "./icons.jsx";

// Solid base-colour rail (mockup style). Lists the saved conversations, opens a
// new chat, and collapses via the panel button. The active conversation is
// passed in full (with messages) so its title can fall back to the first line.
export default function Sidebar({
  open,
  conversations,
  activeId,
  onNewChat,
  onSelect,
  onDelete,
  onClearHistory,
  onOpenSettings,
  onCollapse,
}) {
  return (
    <div
      className="flex-shrink-0 overflow-hidden"
      style={{
        width: open ? 266 : 0,
        transition: "width 0.28s cubic-bezier(0.22, 1, 0.36, 1)",
      }}
    >
      <aside
        className="flex h-full w-[266px] flex-col"
        style={{ background: "var(--sidebar-bg)", borderRight: "1px solid var(--sidebar-border)" }}
      >
      <div className="px-[18px] pb-1 pt-5">
        <div className="flex items-center justify-between">
          <div
            className="font-serif text-2xl"
            style={{
              fontWeight: "var(--wordmark-weight)",
              letterSpacing: "var(--wordmark-tracking)",
              color: "var(--text)",
            }}
          >
            Noema
          </div>
          <button
            onClick={onCollapse}
            aria-label="Hide conversations"
            title="Hide conversations"
            className="grid place-items-center"
            style={{ color: "var(--text-faint)" }}
          >
            <PanelIcon size={17} />
          </button>
        </div>
        <div
          className="mt-2 inline-block rounded-md px-2 py-0.5 font-mono text-[10px]"
          style={{ color: "var(--accent)", background: "var(--accent-soft)" }}
        >
          phase 1 · monofield
        </div>
      </div>

      <div className="px-2.5 pb-1 pt-3.5">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-sm transition hover:bg-[var(--row-hover)]"
          style={{ color: "var(--text)" }}
        >
          <span style={{ color: "var(--text-faint)" }}>
            <NewChatIcon size={16} />
          </span>
          New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2.5 py-2">
        <div className="flex items-center justify-between px-2.5 pb-1.5 pt-2">
          <span className="text-[11px] font-medium" style={{ color: "var(--text-faint)" }}>
            Recent
          </span>
          {conversations.length > 0 && (
            <button
              onClick={onClearHistory}
              title="Delete all conversations"
              className="text-[11px] font-medium transition hover:opacity-100"
              style={{ color: "var(--text-faint)" }}
            >
              Clear
            </button>
          )}
        </div>

        {conversations.length === 0 ? (
          <p className="px-2.5 pt-1 text-[13px]" style={{ color: "var(--text-faint)" }}>
            No conversations yet.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((c) => {
              const isActive = c.id === activeId;
              return (
                <li key={c.id} className="group/row relative">
                  <button
                    onClick={() => onSelect(c.id)}
                    className="flex w-full items-center gap-2.5 truncate rounded-[9px] py-1.5 pl-2.5 pr-8 text-left text-[13.5px] transition hover:bg-[var(--row-hover)]"
                    style={
                      isActive
                        ? { background: "var(--row-active)", color: "var(--text)", fontWeight: 500 }
                        : { color: "var(--text-soft)" }
                    }
                  >
                    <span className="flex-shrink-0" style={{ color: "var(--text-faint)" }}>
                      <Icon size={14} sw={1.6}>
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </Icon>
                    </span>
                    <span className="truncate">{titleOf(c)}</span>
                  </button>
                  <button
                    onClick={() => onDelete(c.id)}
                    aria-label="Delete chat"
                    title="Delete chat"
                    className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded-md p-1 group-hover/row:block"
                    style={{ color: "var(--text-faint)" }}
                  >
                    <TrashIcon size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="p-2.5" style={{ borderTop: "1px solid var(--sidebar-border)" }}>
        <button
          onClick={onOpenSettings}
          aria-label="Open settings"
          title="Settings"
          className="flex w-full items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-sm transition hover:bg-[var(--row-hover)]"
          style={{ color: "var(--text-soft)" }}
        >
          <GearIcon size={16} />
          Settings
        </button>
        </div>
      </aside>
    </div>
  );
}

// Prefer the LLM auto-title; fall back to the first user message, then a stub.
function titleOf(conversation) {
  if (conversation.title) return conversation.title;
  const firstUser = conversation.messages?.find((m) => m.role === "user");
  return firstUser ? firstUser.content : "New chat";
}
