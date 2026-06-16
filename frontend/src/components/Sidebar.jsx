// Dark left rail, ChatGPT style. Lists the in-memory conversations and lets you
// switch between them. Hidden on small screens.
export default function Sidebar({
  conversations,
  activeId,
  onOpenSettings,
  onNewChat,
  onSelect,
  onDelete,
  onClearHistory,
}) {
  return (
    <aside className="hidden w-64 shrink-0 flex-col bg-zinc-900 p-3 text-zinc-100 md:flex">
      <div className="mb-3 flex items-center gap-2 px-1 py-1">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-white text-xs font-bold tracking-tight text-zinc-900">
          N
        </div>
        <span className="text-lg font-semibold tracking-tight text-white">
          Noema
        </span>
      </div>
      <button
        onClick={onNewChat}
        className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:from-indigo-600 hover:to-violet-700"
      >
        <PlusIcon className="h-4 w-4" />
        New chat
      </button>

      <div className="mt-4 flex-1 overflow-y-auto">
        <div className="flex items-center justify-between px-2">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Recent
          </p>
          {conversations.length > 0 && (
            <button
              onClick={onClearHistory}
              title="Delete all conversations"
              className="text-xs font-medium text-zinc-500 transition hover:text-red-400"
            >
              Clear
            </button>
          )}
        </div>
        {conversations.length === 0 ? (
          <p className="mt-2 px-2 text-sm text-zinc-500">
            No conversations yet.
          </p>
        ) : (
          <ul className="mt-2 space-y-1">
            {conversations.map((c) => (
              <li key={c.id} className="group relative">
                <button
                  onClick={() => onSelect(c.id)}
                  className={`w-full truncate rounded-lg py-2 pl-2 pr-8 text-left text-sm transition ${
                    c.id === activeId
                      ? "bg-white/10 text-white"
                      : "text-zinc-300 hover:bg-white/5"
                  }`}
                >
                  {titleOf(c)}
                </button>
                <button
                  onClick={() => onDelete(c.id)}
                  aria-label="Delete chat"
                  title="Delete chat"
                  className="absolute right-1 top-1/2 hidden -translate-y-1/2 rounded p-1 text-zinc-400 transition hover:bg-white/10 hover:text-red-400 group-hover:block"
                >
                  <TrashIcon className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-white/10 pt-3">
        <div className="flex items-center gap-2 px-2 py-1.5 text-sm text-zinc-300">
          <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white/10 text-zinc-200">
            <UserIcon className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1 font-medium text-zinc-100">User</div>
          <button
            onClick={onOpenSettings}
            aria-label="Open settings"
            className="grid h-8 w-8 place-items-center rounded-lg text-zinc-400 transition hover:bg-white/10 hover:text-zinc-100"
          >
            <GearIcon className="h-5 w-5" />
          </button>
        </div>
      </div>
    </aside>
  );
}

// Prefer the LLM auto-title; fall back to the first user message, then a stub.
function titleOf(conversation) {
  if (conversation.title) return conversation.title;
  const firstUser = conversation.messages?.find((m) => m.role === "user");
  return firstUser ? firstUser.content : "New chat";
}

function GearIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function TrashIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

function PlusIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function UserIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}
