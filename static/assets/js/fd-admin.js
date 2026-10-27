/* ==========================================================================
   O'Toosin Farms Admin — admin shell + login controller
   --------------------------------------------------------------------------
   Vanilla JS, no dependencies, no framework. This file NEVER touches the
   customer cart (no dependency on fresh-direct.js cart store) so customer
   state cannot leak into the admin.

   Sections:
     1. Year                    - footer year without template edits.
     2. Shell                   - mobile drawer + active nav + logout slot.
     3. Auth boundary           - window.FreshDirectAdminAuth. THE seam where
                                  Django authentication connects later.
     4. Login form              - validation + UI only. No real auth here.

   DJANGO INTEGRATION (later stage, no frontend redesign needed):
     - Implement signIn() to POST credentials (with CSRF) to the Django
       session/token endpoint and resolve with the seller profile.
     - Implement signOut() to invalidate the server session, then redirect.
     - Implement requestPasswordReset() against the Django reset endpoint.
     - Gate admin pages server-side; this file only mirrors that state.
   ========================================================================== */
(function () {
  "use strict";

  /* ---------- 1. Footer year ---------- */
  function wireYear() {
    var nodes = document.querySelectorAll("[data-fd-year]");
    var year = String(new Date().getFullYear());
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = year;
    }
  }

  /* ---------- 2. Admin shell: drawer navigation ---------- */
  function wireShell() {
    var shell = document.querySelector(".fd-admin-shell");
    if (!shell) {
      return;
    }
    var toggle = document.getElementById("fd-admin-menu-btn");
    var scrim = document.getElementById("fd-admin-scrim");
    var sidebar = document.getElementById("fd-admin-sidebar");
    if (!toggle || !scrim || !sidebar) {
      return;
    }
    var lastFocus = null;

    function isOpen() {
      return shell.classList.contains("nav-open");
    }

    function open() {
      lastFocus = document.activeElement;
      shell.classList.add("nav-open");
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "Close admin menu");
      document.body.style.overflow = "hidden";
      var first = sidebar.querySelector("a, button:not([aria-disabled='true'])");
      if (first) {
        first.focus();
      }
    }

    function close(returnFocus) {
      if (!isOpen()) {
        return;
      }
      shell.classList.remove("nav-open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open admin menu");
      document.body.style.overflow = "";
      if (returnFocus && lastFocus && document.contains(lastFocus)) {
        lastFocus.focus();
      } else {
        toggle.focus();
      }
    }

    toggle.addEventListener("click", function () {
      if (isOpen()) {
        close(false);
      } else {
        open();
      }
    });

    scrim.addEventListener("click", function () {
      close(true);
    });

    document.addEventListener("keydown", function (ev) {
      if ((ev.key === "Escape" || ev.key === "Esc") && isOpen()) {
        close(true);
      }
    });

    // Choosing an enabled destination closes the drawer (future stages).
    sidebar.addEventListener("click", function (ev) {
      var link = ev.target.closest("a.fd-admin-nav-link");
      if (link) {
        close(false);
      }
    });
  }

  /* ---------- 3. Authentication boundary ----------
     Django owns real authentication. These functions are the ONLY place the
     login UI talks to "auth", so connecting the backend means editing this
     section — never the form markup or validation above it.

     Current behavior is deliberately non-functional: every method rejects
     with code "AUTH_NOT_CONFIGURED". The UI surfaces that as a neutral,
     clearly development-only notice. There are no hardcoded credentials,
     no fake sessions, and no fabricated success state anywhere. */
  var AUTH_NOT_CONFIGURED = "AUTH_NOT_CONFIGURED";

  function notConfigured(op) {
    var err = new Error(
      "O'Toosin Farms admin authentication is not connected yet (" + op + ")."
    );
    err.code = AUTH_NOT_CONFIGURED;
    return err;
  }

  window.FreshDirectAdminAuth = {
    /**
     * Attempt seller sign-in. Django stage: POST {email, password, remember}
     * to the backend login endpoint and resolve with the seller profile.
     * Today: always rejects with AUTH_NOT_CONFIGURED (no session created).
     */
    signIn: function (credentials) {
      void credentials;
      return Promise.reject(notConfigured("signIn"));
    },
    /**
     * Start a password reset. Django stage: POST {email} to the reset
     * endpoint (backend sends the email + token, never the frontend).
     * Today: always rejects with AUTH_NOT_CONFIGURED (nothing is sent).
     */
    requestPasswordReset: function (email) {
      void email;
      return Promise.reject(notConfigured("requestPasswordReset"));
    },
    /**
     * End the admin session. Django stage: invalidate the server session
     * (POST logout / clear token) and resolve when done.
     * Today: always rejects with AUTH_NOT_CONFIGURED.
     */
    signOut: function () {
      return Promise.reject(notConfigured("signOut"));
    },
  };

  /* ---------- 4. Login form: validation + boundary wiring ---------- */
  function setFieldError(input, errorEl, message) {
    if (!input || !errorEl) {
      return;
    }
    if (message) {
      errorEl.textContent = message;
      errorEl.removeAttribute("hidden");
      input.setAttribute("aria-invalid", "true");
    } else {
      errorEl.textContent = "";
      errorEl.setAttribute("hidden", "");
      input.removeAttribute("aria-invalid");
    }
  }

  function wirePasswordToggle() {
    var toggle = document.getElementById("fd-admin-pass-toggle");
    var input = document.getElementById("fd-admin-password");
    if (!toggle || !input) {
      return;
    }
    toggle.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.setAttribute("aria-pressed", show ? "true" : "false");
      toggle.setAttribute(
        "aria-label",
        show ? "Hide password" : "Show password"
      );
      var icon = toggle.querySelector("i");
      if (icon) {
        icon.className = show ? "far fa-eye-slash" : "far fa-eye";
      }
      input.focus();
    });
  }

  function wireForgotPanel() {
    var toggle = document.getElementById("fd-admin-forgot");
    var panel = document.getElementById("fd-admin-forgot-panel");
    if (!toggle || !panel) {
      return;
    }
    toggle.addEventListener("click", function () {
      var open = panel.hasAttribute("hidden");
      if (open) {
        panel.removeAttribute("hidden");
        toggle.setAttribute("aria-expanded", "true");
      } else {
        panel.setAttribute("hidden", "");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
    // The panel is guidance only: the farm owner manages staff credentials.
    // No reset request is sent and no email flow is implied.
  }

  function wireLoginForm() {
    var form = document.getElementById("fd-admin-login-form");
    if (!form) {
      return;
    }
    var email = document.getElementById("fd-admin-email");
    var password = document.getElementById("fd-admin-password");
    var remember = document.getElementById("fd-admin-remember");
    var emailError = document.getElementById("fd-admin-email-error");
    var passwordError = document.getElementById("fd-admin-password-error");
    var status = document.getElementById("fd-admin-status");
    var submit = document.getElementById("fd-admin-submit");
    var submitLabel = document.getElementById("fd-admin-submit-label");
    var submitIcon = submit ? submit.querySelector("i") : null;

    function setBusy(busy) {
      if (!submit) {
        return;
      }
      submit.disabled = busy;
      if (busy) {
        submit.setAttribute("aria-busy", "true");
        if (submitLabel) {
          submitLabel.textContent = "Signing in…";
        }
        if (submitIcon) {
          submitIcon.className = "fas fa-spinner fa-spin";
        }
      } else {
        submit.removeAttribute("aria-busy");
        if (submitLabel) {
          submitLabel.textContent = "Sign in";
        }
        if (submitIcon) {
          submitIcon.className = "fas fa-sign-in-alt";
        }
      }
    }

    function showStatus(kind, title, text) {
      if (!status) {
        return;
      }
      status.className = "fd-admin-notice" + (kind ? " " + kind : "");
      status.innerHTML = "";
      var strong = document.createElement("strong");
      strong.textContent = title;
      status.appendChild(strong);
      status.appendChild(document.createTextNode(text));
      status.removeAttribute("hidden");
    }

    function hideStatus() {
      if (status) {
        status.setAttribute("hidden", "");
      }
    }

    function validEmail(value) {
      // Format check only (UI-level). Existence is never probed: failures
      // stay generic so the UI cannot reveal whether an account exists.
      return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (submit && submit.disabled) {
        return;
      }
      hideStatus();
      var emailValue = email ? email.value.trim() : "";
      var passwordValue = password ? password.value : "";
      var ok = true;

      if (!emailValue) {
        setFieldError(email, emailError, "Enter your work email address.");
        ok = false;
      } else if (!validEmail(emailValue)) {
        setFieldError(email, emailError, "Enter a valid email address.");
        ok = false;
      } else {
        setFieldError(email, emailError, "");
      }

      if (!passwordValue) {
        setFieldError(password, passwordError, "Enter your password.");
        ok = false;
      } else {
        setFieldError(password, passwordError, "");
      }

      if (!ok) {
        showStatus(
          "is-error",
          "Check the highlighted fields.",
          "Fix the errors above and try again."
        );
        var firstInvalid = form.querySelector("[aria-invalid='true']");
        if (firstInvalid) {
          firstInvalid.focus();
        }
        return;
      }

      setBusy(true);

      window.FreshDirectAdminAuth.signIn({
        email: emailValue,
        password: passwordValue,
        remember: !!(remember && remember.checked),
      }).then(
        function () {
          // Unreachable until Django connects the boundary. Kept so the
          // success path has exactly one place to land in a later stage.
          setBusy(false);
        },
        function (err) {
          setBusy(false);
          if (err && err.code === AUTH_NOT_CONFIGURED) {
            // Honest boundary state: this page does not check passwords and
            // never implies an account-existence result or a fake session.
            showStatus(
              "is-error",
              "Sign-in is not connected.",
              "This page does not verify staff passwords. Access is managed " +
                "by the farm owner."
            );
          } else {
            showStatus(
              "is-error",
              "Could not sign in.",
              "Something went wrong. Please try again."
            );
          }
        }
      );
    });

    // Clear a field's error as soon as the seller corrects it.
    if (email) {
      email.addEventListener("input", function () {
        setFieldError(email, emailError, "");
      });
    }
    if (password) {
      password.addEventListener("input", function () {
        setFieldError(password, passwordError, "");
      });
    }
  }

  function wireLogout() {
    var btn = document.getElementById("fd-admin-logout");
    if (!btn) {
      return;
    }
    btn.addEventListener("click", function () {
      // Disabled until a real session exists; the backend stage enables it.
      if (btn.getAttribute("aria-disabled") === "true") {
        return;
      }
      window.FreshDirectAdminAuth.signOut().catch(function () {
        /* Surfaced by the owning page once sessions exist. */
      });
    });
  }

  /* ---------- 5. Mobile base navigation ----------
     Mirrors the storefront's fixed mobile base nav: five primary admin
     destinations with an icon, a short label and a clear active state.
     The desktop sidebar stays exactly as it is; this bar is mobile-only
     and is never injected into the standalone sign-in screen. */
  function wireBaseNav() {
    var shell = document.querySelector(".fd-admin-shell");
    if (!shell || document.getElementById("fd-admin-login-form")) {
      return;
    }
    if (document.querySelector(".fd-admin-base-nav")) {
      return;
    }

    var file = window.location.pathname
      .replace(/\\/g, "/")
      .split("/")
      .pop()
      .toLowerCase();
    if (!file) {
      file = "admin-dashboard.html";
    }

    var activeMap = {
      "admin-dashboard.html": "dashboard",
      "admin-orders.html": "orders",
      "admin-order.html": "orders",
      "admin-products.html": "products",
      "admin-product-edit.html": "products",
      "admin-inventory.html": "inventory",
      "admin-categories.html": "categories"
    };
    var active = activeMap[file] || "";

    var items = [
      {
        key: "dashboard",
        label: "Dashboard",
        href: "admin-dashboard.html",
        icon: "fas fa-tachometer-alt"
      },
      {
        key: "orders",
        label: "Orders",
        href: "admin-orders.html",
        icon: "fas fa-receipt"
      },
      {
        key: "products",
        label: "Products",
        href: "admin-products.html",
        icon: "fas fa-box"
      },
      {
        key: "inventory",
        label: "Inventory",
        href: "admin-inventory.html",
        icon: "fas fa-warehouse"
      },
      {
        key: "categories",
        label: "Categories",
        href: "admin-categories.html",
        icon: "fas fa-layer-group"
      }
    ];

    var nav = document.createElement("nav");
    nav.className = "fd-admin-base-nav";
    nav.setAttribute("aria-label", "Admin quick navigation");

    var list = document.createElement("ul");
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var li = document.createElement("li");
      var link = document.createElement("a");
      link.className = "fd-admin-base-nav__item";
      link.href = item.href;
      if (active === item.key) {
        link.className += " is-active";
        link.setAttribute("aria-current", "page");
      }

      var iconWrap = document.createElement("span");
      iconWrap.className = "fd-admin-base-nav__icon";
      iconWrap.setAttribute("aria-hidden", "true");
      var icon = document.createElement("i");
      icon.className = item.icon;
      iconWrap.appendChild(icon);

      var label = document.createElement("span");
      label.className = "fd-admin-base-nav__label";
      label.textContent = item.label;

      link.appendChild(iconWrap);
      link.appendChild(label);
      li.appendChild(link);
      list.appendChild(li);
    }

    nav.appendChild(list);
    document.body.appendChild(nav);
    document.body.classList.add("fd-admin-base-nav-on");
  }

  /* Paint the mobile base navigation as soon as the shell is parsed, so the
     bottom of small screens is covered from first paint instead of waiting
     for DOMContentLoaded (which can be delayed by slow font/asset requests).
     The DOMContentLoaded call below remains as a no-op safety net. */
  wireBaseNav();

  document.addEventListener("DOMContentLoaded", function () {
    wireYear();
    wireShell();
    wireBaseNav();
    wirePasswordToggle();
    wireForgotPanel();
    wireLoginForm();
    wireLogout();
  });
})();
