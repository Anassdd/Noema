import { useEffect, useState } from "react";

const THEME_KEY = "noema-theme-family";
const THEME_FAMILIES = ["aurora", "codex"];

function readThemeFamily() {
  const saved = window.localStorage.getItem(THEME_KEY);
  return THEME_FAMILIES.includes(saved) ? saved : "aurora";
}

// Session-level feature switches (default on) plus appearance (dark mode +
// theme family). memoryEnabled is the master switch (off = no capture, no
// injection of saved facts). prefilterEnabled gates the auto-judge with the
// cheap regex (off = judge every turn). tokenizerEnabled shows the live token
// estimate while typing.
export function useSettings() {
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [prefilterEnabled, setPrefilterEnabled] = useState(true);
  const [tokenizerEnabled, setTokenizerEnabled] = useState(true);
  const [darkMode, setDarkMode] = useState(false);
  const [themeFamily, setThemeFamily] = useState(readThemeFamily);

  // Dark mode = a `dark` class on <html>; the theme family = a `data-theme`
  // attribute (absent for the default "aurora"). Both read the same token vars,
  // so the CSS handles the rest. The temporary theme-transition class cross-
  // fades every color for the switch instead of snapping.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add("theme-transition");
    root.classList.toggle("dark", darkMode);
    if (themeFamily === "aurora") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", themeFamily);
    window.localStorage.setItem(THEME_KEY, themeFamily);
    const timer = window.setTimeout(
      () => root.classList.remove("theme-transition"),
      350,
    );
    return () => window.clearTimeout(timer);
  }, [darkMode, themeFamily]);

  return {
    memoryEnabled,
    toggleMemory: () => setMemoryEnabled((on) => !on),
    prefilterEnabled,
    togglePrefilter: () => setPrefilterEnabled((on) => !on),
    tokenizerEnabled,
    toggleTokenizer: () => setTokenizerEnabled((on) => !on),
    darkMode,
    toggleDarkMode: () => setDarkMode((on) => !on),
    themeFamily,
    setThemeFamily,
  };
}
