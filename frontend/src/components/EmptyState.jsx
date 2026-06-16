// First-run screen: just a centered greeting.
export default function EmptyState() {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-4 text-center">
      <h1 className="text-2xl font-semibold text-zinc-800 dark:text-zinc-100">
        How can I help you today?
      </h1>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">Ask anything to get started.</p>
    </div>
  );
}
