// Light/dark switch. Until the user picks, the theme follows the system setting; a pick is
// remembered in this browser. An inline script in each page's <head> applies the saved pick
// before the first paint, so there is no flash of the wrong theme.
const KEY = "storyteller-theme";
const media = matchMedia("(prefers-color-scheme: dark)");
const root = document.documentElement;

const current = () => root.dataset.theme || (media.matches ? "dark" : "light");

export function bindThemeToggle(btn) {
  const sync = () => btn.setAttribute("aria-pressed", String(current() === "dark"));
  btn.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
    sync();
  });
  media.addEventListener("change", sync);
  sync();
}
