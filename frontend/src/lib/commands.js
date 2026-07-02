// The slash commands ChatWindow.send() understands — the single source of
// truth for the autocomplete menu, the in-input coloring, the command chip,
// and the /help card. Each command has its own color (cyan/violet/rose/amber/
// emerald; indigo is reserved for the app accent).
export const COMMANDS = [
  {
    cmd: "/remember",
    label: "Memory",
    desc: "Save a fact across all chats",
    usage: "/remember I prefer short answers",
    hint: "Facts persist on disk and are fed to the model in every chat.",
    text: "text-cyan-600 dark:text-cyan-400",
    chip: "bg-cyan-50 text-cyan-700 ring-cyan-200 dark:bg-cyan-950/40 dark:text-cyan-300 dark:ring-cyan-900",
  },
  {
    cmd: "/note",
    label: "Note",
    desc: "Add a note to the current memory",
    usage: "/note Q1 revenue beat guidance",
    hint: "Saved to the selected memory's beliefs; the expert weighs it against the sources.",
    text: "text-teal-600 dark:text-teal-400",
    chip: "bg-teal-50 text-teal-700 ring-teal-200 dark:bg-teal-950/40 dark:text-teal-300 dark:ring-teal-900",
  },
  {
    cmd: "/character",
    label: "Persona",
    desc: "Set the bot's character or role",
    usage: "/character a witty pirate captain",
    hint: "Per-conversation. Also editable from the Persona button up top.",
    text: "text-violet-600 dark:text-violet-400",
    chip: "bg-violet-50 text-violet-700 ring-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:ring-violet-900",
  },
  {
    cmd: "/forget",
    label: "Forget",
    desc: "Remove a saved fact",
    usage: "/forget short answers",
    hint: "Matches any part of the fact's text; removes the first match.",
    text: "text-rose-600 dark:text-rose-400",
    chip: "bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900",
  },
  {
    cmd: "/clear",
    label: "Clear",
    desc: "Clear this conversation",
    usage: "/clear",
    hint: "Wipes the transcript only — memory and attached PDFs stay.",
    text: "text-amber-600 dark:text-amber-400",
    chip: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-900",
  },
  {
    cmd: "/help",
    label: "Help",
    desc: "Show this command guide",
    usage: "/help",
    hint: "Tip: type / and pick a command with ↑↓ + Enter.",
    text: "text-emerald-600 dark:text-emerald-400",
    chip: "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900",
  },
];

// Split a leading "/word" from the rest and return the matching command (exact
// word) plus the `word` / `rest` split, or null. Used to color the input.
export function findCommand(text) {
  const m = text.match(/^(\/[a-zA-Z]+)([\s\S]*)$/);
  if (!m) return null;
  const hit = COMMANDS.find((c) => c.cmd === m[1].toLowerCase());
  return hit ? { ...hit, word: m[1], rest: m[2] } : null;
}

// Autocomplete: while the text is just a partial command ("/", "/re"…), offer
// the matching commands.
export function matchCommands(text) {
  if (!/^\/[a-z]*$/i.test(text)) return [];
  const lower = text.toLowerCase();
  return COMMANDS.filter((c) => c.cmd.startsWith(lower) && c.cmd !== lower);
}
