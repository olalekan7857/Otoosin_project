/* ==========================================================================
   Harvest Castle — Light/Dark theme controller (Stage: global theme system)
   --------------------------------------------------------------------------
   Zero-dependency, vanilla JS. Loaded on every Harvest Castle page AFTER the
   page's own scripts (storefront: after fresh-direct.js; admin: after
   fd-admin.js) so it can never interfere with cart, checkout, menu or
   admin behaviour. All theme state lives on <html data-theme="dark">;
   absence of the attribute (or any value other than "dark") means Light.

   Conventions mirrored from the project:
     storage -> versioned localStorage key + try/catch fallback, same as
                freshdirect_cart_v1 (fresh-direct.js) and the
                freshdirect_admin_*_v1 admin stores.
     hooks   -> data attributes ([data-theme-toggle]), same pattern as
                [data-whatsapp] / [data-add-to-cart].
     guards  -> every wire is a no-op when its elements are absent, same
                as the wire*() functions in fresh-direct.js / fd-admin.js.

   Django-ready: window.FreshDirectTheme { get, set, toggle, THEME_KEY }
   is the single integration point. A backend can seed the initial theme
   by rendering <html data-theme="dark"> server-side; this script adopts
   the rendered value on boot and persists later changes to localStorage.
   ========================================================================== */
(function () {
  "use strict";

  var THEME_KEY = "freshdirect_theme_v1";
  var DARK = "dark";
  var LIGHT = "light";
  var META_LIGHT = "#ffffff";
  var META_DARK = "#0d120f";

  function readStored() {
    try {
      return window.localStorage.getItem(THEME_KEY) === DARK ? DARK : LIGHT;
    } catch (err) {
      return LIGHT;
    }
  }

  function persist(theme) {
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch (err) {
      /* Private mode / blocked storage: theme still applies for this page. */
    }
  }

  function current() {
    return document.documentElement.getAttribute("data-theme") === DARK ? DARK : LIGHT;
  }

  /* Keep the browser chrome (and any server-rendered meta) in sync. */
  function syncMeta(theme) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "theme-color");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", theme === DARK ? META_DARK : META_LIGHT);
  }

  function syncToggleButtons(theme) {
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      var isDark = theme === DARK;
      btn.setAttribute("aria-pressed", isDark ? "true" : "false");
      btn.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
      btn.setAttribute("title", isDark ? "Switch to light mode" : "Switch to dark mode");
      var icons = btn.querySelectorAll("[data-theme-icon]");
      for (var j = 0; j < icons.length; j++) {
        var show = icons[j].getAttribute("data-theme-icon") === (isDark ? "sun" : "moon");
        if (show) {
          icons[j].removeAttribute("hidden");
        } else {
          icons[j].setAttribute("hidden", "");
        }
      }
    }
  }

  function paint(theme) {
    if (theme === DARK) {
      document.documentElement.setAttribute("data-theme", DARK);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    syncMeta(theme);
    syncToggleButtons(theme);
  }

  function setTheme(theme, options) {
    var next = theme === DARK ? DARK : LIGHT;
    paint(next);
    if (!options || options.persist !== false) {
      persist(next);
    }
    return next;
  }

  function toggleTheme() {
    return setTheme(current() === DARK ? LIGHT : DARK);
  }

  function wireToggles() {
    /* Delegated single listener: any present or future toggle just works. */
    document.addEventListener("click", function (event) {
      var btn = event.target && event.target.closest
        ? event.target.closest("[data-theme-toggle]")
        : null;
      if (!btn) {
        return;
      }
      event.preventDefault();
      toggleTheme();
    });
  }

  function boot() {
    /* Adopt a server-rendered value first (Django-ready); otherwise the
       stored preference; otherwise Light (the approved default). */
    var rendered = document.documentElement.getAttribute("data-theme");
    var initial = rendered === DARK ? DARK : readStored();
    paint(initial);
    wireToggles();
  }

  window.FreshDirectTheme = {
    THEME_KEY: THEME_KEY,
    LIGHT: LIGHT,
    DARK: DARK,
    get: current,
    set: setTheme,
    toggle: toggleTheme
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
