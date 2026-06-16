// Small on/off switch. Greys out and ignores clicks when disabled.
export default function Toggle({ on, onClick, disabled, label }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={`relative h-5 w-9 shrink-0 rounded-full transition ${
        on ? "bg-indigo-600" : "bg-zinc-300 dark:bg-zinc-600"
      } ${disabled ? "cursor-not-allowed opacity-40" : ""}`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${
          on ? "left-[18px]" : "left-0.5"
        }`}
      />
    </button>
  );
}
