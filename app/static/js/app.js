// InterviewCoach: small client helpers (theme toggle, sample-answer fill).
(function () {
  "use strict";

  // ---- Theme (light/dark) with persistence + system fallback -------------
  const root = document.documentElement;
  const THEME_KEY = "interviewcoach-theme";

  function applyTheme(theme) {
    if (theme === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
  }

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) {
      applyTheme(saved);
    } else {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      applyTheme(prefersDark ? "dark" : "light");
    }
  }

  window.toggleTheme = function () {
    const isDark = root.classList.toggle("dark");
    localStorage.setItem(THEME_KEY, isDark ? "dark" : "light");
  };

  // ---- Drop a strong example answer into the focused question form -------
  // Lets a visitor experience scoring instantly without writing prose.
  window.fillSampleAnswer = function (btn) {
    const form = btn.closest("[data-answer-form]");
    if (!form) return;
    const ta = form.querySelector("textarea[name='answer_text']");
    if (!ta) return;
    ta.value = btn.getAttribute("data-sample") || "";
    ta.focus();
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  };

  // Initialize theme as early as possible to avoid a flash.
  initTheme();
})();
