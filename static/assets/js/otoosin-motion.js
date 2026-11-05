/* ==========================================================================
   O’TOOSIN Farms — shared motion controller
   --------------------------------------------------------------------------
   Adds a small entrance transition to selected sections and cards as they
   enter the viewport. It never hides content when JavaScript is unavailable
   because the `.fd-motion` class is only applied here.

   No animation library, no scroll listeners, no layout reads in a loop.
   ========================================================================== */
(function () {
  "use strict";

  var SELECTOR = [
    /* Storefront */
    ".oto-hero-content",
    ".oto-hero-media",
    ".oto-service-item",
    "#categories .title-area",
    "#categories .fd-cat-cell",
    "#featured .title-area",
    "#featured .product-style1",
    "#fd-home-grid .product-style1",
    ".oto-shop-intro",
    ".fd-shop-toolbar",
    ".oto-shop-list-section .product-style1",
    ".oto-shop-category",
    ".oto-category-hero",
    ".oto-category-nav",
    ".fd-pdp-gallery",
    ".oto-pdp-info",
    ".oto-pdp-know-grid > *",
    "#fd-pdp-related .product-style1",
    ".oto-cart-panel",
    ".oto-cart-summary",
    ".oto-checkout-guest",
    ".fd-checkout-card",
    ".oto-checkout-summary",
    ".oto-band-inner",
    ".oto-error-panel",
    /* Admin */
    ".fd-dash-head",
    ".fd-dash-section",
    ".fd-dash-card",
    ".fd-settings-section",
    ".fd-team-card",
    ".fd-prod-card",
    ".fd-admin-denied"
  ].join(",");

  var STAGGER = /(card|cell|service-item|product-style1|oto-shop-category)/;

  function revealAll(elements) {
    for (var i = 0; i < elements.length; i++) {
      elements[i].classList.add("fd-motion-in");
    }
  }

  function init() {
    if (!("IntersectionObserver" in window)) {
      return;
    }
    if (
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }

    var elements = document.querySelectorAll(SELECTOR);
    if (!elements.length) {
      return;
    }

    var observer;
    try {
      observer = new IntersectionObserver(
        function (entries) {
          for (var i = 0; i < entries.length; i++) {
            var entry = entries[i];
            if (!entry.isIntersecting) {
              continue;
            }
            entry.target.classList.add("fd-motion-in");
            observer.unobserve(entry.target);
          }
        },
        { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
      );
    } catch (error) {
      return;
    }

    var parentCounts = new WeakMap();
    var viewportTrigger = (window.innerHeight || 0) * 0.92;

    for (var i = 0; i < elements.length; i++) {
      var element = elements[i];
      if (element.classList.contains("fd-motion-in")) {
        continue;
      }
      /* Anything already on screen stays visible from first paint. Its
         gentle load animation lives in CSS; only below-fold content waits
         for the observer, so there is no flash of hidden content. */
      if (element.getBoundingClientRect().top < viewportTrigger) {
        element.classList.add("fd-motion-in");
        continue;
      }
      if (STAGGER.test(element.className || "")) {
        var parent = element.parentElement;
        var count = parentCounts.get(parent) || 0;
        parentCounts.set(parent, count + 1);
        element.style.setProperty(
          "--fd-motion-delay",
          Math.min(count, 6) * 55 + "ms"
        );
      }
      element.classList.add("fd-motion");
      observer.observe(element);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  /* Content injected later (filters, AJAX grids) should never stay hidden.
     Exposed for page scripts that want to opt in after rendering. */
  window.OtoosinMotion = {
    reveal: function (root) {
      var scope = root || document;
      revealAll(scope.querySelectorAll(".fd-motion:not(.fd-motion-in)"));
    }
  };
})();
