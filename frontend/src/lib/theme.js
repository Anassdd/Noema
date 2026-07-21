// Appearance = a `dark` class on <html> plus a `data-theme` attribute for the
// family (absent for the default "aurora"). Both persist in localStorage so
// every surface — including the login gate, which renders before the app and
// its settings hook — can apply the saved look immediately.

const FAMILY_KEY = "noema-theme-family";
const DARK_KEY = "noema-dark";
const FAMILIES = ["aurora", "codex"];

export function savedThemeFamily() {
  const saved = window.localStorage.getItem(FAMILY_KEY);
  return FAMILIES.includes(saved) ? saved : "aurora";
}

export function savedDarkMode() {
  const saved = window.localStorage.getItem(DARK_KEY);
  if (saved === "1" || saved === "0") return saved === "1";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

let _animTimer = null;

// Cross-fades every surface when the LOOK actually changes (toggling dark mode or
// switching family). The class is temporary: leaving transitions on permanently
// would smear hover states and panel animations everywhere.
function animateChange(root, darkMode, themeFamily) {
  const current = root.getAttribute("data-theme") || "aurora";
  if (root.classList.contains("dark") === darkMode && current === themeFamily) return;
  root.classList.add("theme-anim");
  clearTimeout(_animTimer);
  _animTimer = setTimeout(() => root.classList.remove("theme-anim"), 500);
}

export function applyTheme(darkMode, themeFamily) {
  const root = document.documentElement;
  animateChange(root, darkMode, themeFamily);
  root.classList.toggle("dark", darkMode);
  if (themeFamily === "aurora") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", themeFamily);
  window.localStorage.setItem(DARK_KEY, darkMode ? "1" : "0");
  window.localStorage.setItem(FAMILY_KEY, themeFamily);
}

export function applySavedTheme() {
  applyTheme(savedDarkMode(), savedThemeFamily());
}
