(function () {
  "use strict";

  if (window.OtoosinMobileNav && window.OtoosinMobileNav.initialized) {
    return;
  }

  var thisScript = document.currentScript;
  if (!thisScript) {
    thisScript = document.querySelector('script[src$="otoosin-mobile-nav.js"]');
  }

  var fragmentUrl;
  try {
    fragmentUrl = new URL(
      "../../partials/otoosin-mobile-nav.html",
      thisScript && thisScript.src ? thisScript.src : document.baseURI
    ).href;
  } catch (error) {
    fragmentUrl = "partials/otoosin-mobile-nav.html";
  }

  var state = {
    initialized: false,
    fragmentUrl: fragmentUrl,
    mountSelector: "[data-otoosin-mobile-nav-mount]",
    navSelector: "[data-otoosin-mobile-nav]"
  };

  window.OtoosinMobileNav = state;

  function onReady(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  }

  function warn(message) {
    if (window.console && typeof window.console.warn === "function") {
      window.console.warn("[O'Toosin mobile nav] " + message);
    }
  }

  function currentFile() {
    var path = window.location.pathname.replace(/\\/g, "/");
    var file = path.substring(path.lastIndexOf("/") + 1);
    return file ? file.toLowerCase() : "index.html";
  }

  function activeMatch() {
    var file = currentFile();
    var map = {
      "index.html": "home",
      "product.html": "shop",
      "product-category.html": "shop",
      "product-details.html": "shop",
      "cart.html": "cart",
      "checkout.html": "cart",
      "order-confirmation.html": "cart",
      "contact.html": "help"
    };
    return map[file] || "";
  }

  function setActiveItem(nav) {
    var active = activeMatch();
    var items = nav.querySelectorAll("[data-nav-match]");
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var isActive = active && item.getAttribute("data-nav-match") === active;
      item.classList.toggle("is-active", !!isActive);
      if (isActive) {
        item.setAttribute("aria-current", "page");
      } else {
        item.removeAttribute("aria-current");
      }
    }
  }

  function syncCartBadge(nav) {
    var badge = nav.querySelector("[data-otoosin-cart-badge]");
    var cartLink = nav.querySelector("[data-otoosin-cart-link]");
    if (!badge) {
      return;
    }

    function apply(count) {
      var safeCount = isFinite(count) && count > 0 ? Math.floor(count) : 0;
      if (safeCount > 0) {
        badge.textContent = safeCount > 99 ? "99+" : String(safeCount);
        badge.hidden = false;
        if (cartLink) {
          cartLink.setAttribute(
            "aria-label",
            "Cart, " + safeCount + (safeCount === 1 ? " item" : " items")
          );
        }
      } else {
        badge.textContent = "0";
        badge.hidden = true;
        if (cartLink) {
          cartLink.setAttribute("aria-label", "Cart");
        }
      }
    }

    function readSourceCounts() {
      var sources = document.querySelectorAll(
        "#fd-cart-count, #fd-cart-count-mobile"
      );
      var count = 0;
      for (var i = 0; i < sources.length; i++) {
        var value = parseInt(sources[i].textContent, 10);
        if (isFinite(value) && value > count) {
          count = value;
        }
      }
      return { sources: sources, count: count };
    }

    var initial = readSourceCounts();
    apply(initial.count);

    if (!initial.sources.length || !window.MutationObserver) {
      return;
    }

    var observer = new MutationObserver(function () {
      apply(readSourceCounts().count);
    });

    for (var i = 0; i < initial.sources.length; i++) {
      observer.observe(initial.sources[i], {
        childList: true,
        characterData: true,
        subtree: true
      });
    }
  }

  function focusShopSearch() {
    var input = document.getElementById("fd-shop-search");
    if (!input) {
      return false;
    }

    var reducedMotion =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    try {
      input.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "center"
      });
    } catch (error) {
      input.scrollIntoView();
    }

    window.setTimeout(function () {
      try {
        input.focus({ preventScroll: true });
      } catch (error) {
        input.focus();
      }
    }, reducedMotion ? 0 : 250);

    return true;
  }

  function wireSearch(nav) {
    var link = nav.querySelector("[data-otoosin-search]");
    if (!link) {
      return;
    }

    link.addEventListener("click", function (event) {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      if (focusShopSearch()) {
        event.preventDefault();
      }
    });

    if (window.location.hash === "#fd-shop-search") {
      window.setTimeout(focusShopSearch, 0);
    }
  }

  function setup(nav) {
    if (nav.getAttribute("data-otoosin-mobile-nav-ready") === "true") {
      return;
    }
    nav.setAttribute("data-otoosin-mobile-nav-ready", "true");
    document.body.classList.add("otoosin-mobile-nav-enabled");
    setActiveItem(nav);
    syncCartBadge(nav);
    wireSearch(nav);
  }

  function mountFragment() {
    var nav = document.querySelector(state.navSelector);
    if (nav) {
      setup(nav);
      return;
    }

    var mounts = document.querySelectorAll(state.mountSelector);
    if (!mounts.length) {
      return;
    }

    if (!window.fetch) {
      warn("The browser does not support the fragment loader.");
      return;
    }

    window
      .fetch(state.fragmentUrl, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        for (var i = 0; i < mounts.length; i++) {
          if (!mounts[i].querySelector(state.navSelector)) {
            mounts[i].innerHTML = html;
            break;
          }
        }
        nav = document.querySelector(state.navSelector);
        if (nav) {
          setup(nav);
        }
      })
      .catch(function (error) {
        warn("Could not load the navigation fragment: " + error.message);
      });
  }

  state.initialized = true;
  onReady(mountFragment);
})();
