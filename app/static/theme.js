(function () {
  var STORAGE_KEY = "mtpi-theme";

  function preferred() {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function getTheme() {
    var stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") {
      return stored;
    }
    return preferred();
  }

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      btn.textContent = theme === "dark" ? "Light mode" : "Dark mode";
      btn.title = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
    }
  }

  window.mtpiSetTheme = function (theme) {
    localStorage.setItem(STORAGE_KEY, theme);
    apply(theme);
  };

  document.addEventListener("DOMContentLoaded", function () {
    apply(getTheme());
    var btn = document.getElementById("theme-toggle");
    if (!btn) {
      return;
    }
    btn.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme") || getTheme();
      var next = current === "dark" ? "light" : "dark";
      window.mtpiSetTheme(next);
    });
  });
})();
