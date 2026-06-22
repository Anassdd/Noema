// First-run screen: a centered serif greeting in the Noema theme.
export default function EmptyState() {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-4 text-center">
      <h1 className="font-serif text-[28px]" style={{ color: "var(--text)" }}>
        How can I help you today?
      </h1>
      <p className="mt-2 text-sm" style={{ color: "var(--text-faint)" }}>
        Ask Noema anything to get started.
      </p>
    </div>
  );
}
