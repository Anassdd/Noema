import { useEffect, useState } from "react";

import { applyTheme, onThemeChange, savedDarkMode, savedThemeFamily } from "../lib/theme.js";

// Session-level feature switches (default on) plus appearance (dark mode +
// theme family). memoryEnabled is the master switch (off = no capture, no
// injection of saved facts). prefilterEnabled gates the auto-judge with the
// cheap regex (off = judge every turn). tokenizerEnabled shows the live token
// estimate while typing.
export function useSettings() {
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [prefilterEnabled, setPrefilterEnabled] = useState(true);
  const [tokenizerEnabled, setTokenizerEnabled] = useState(true);
  // Expert mode: ground answers in the RAG/graph knowledge base (retrieve → verify →
  // cite). Off = plain chat. Distinct from memoryEnabled (durable facts about the user).
  const [expertEnabled, setExpertEnabled] = useState(true);
  const [darkMode, setDarkMode] = useState(savedDarkMode);
  const [themeFamily, setThemeFamily] = useState(savedThemeFamily);

  // Appearance lives in lib/theme.js (shared with the login gate) and persists
  // across reloads. The temporary theme-transition class cross-fades every
  // color for the switch instead of snapping.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add("theme-transition");
    applyTheme(darkMode, themeFamily);
    const timer = window.setTimeout(
      () => root.classList.remove("theme-transition"),
      350,
    );
    return () => window.clearTimeout(timer);
  }, [darkMode, themeFamily]);

  // Follow appearance changes made in another tab (e.g. the memory page).
  useEffect(
    () =>
      onThemeChange((dark, family) => {
        setDarkMode(dark);
        setThemeFamily(family);
      }),
    [],
  );

  return {
    memoryEnabled,
    toggleMemory: () => setMemoryEnabled((on) => !on),
    expertEnabled,
    toggleExpert: () => setExpertEnabled((on) => !on),
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
