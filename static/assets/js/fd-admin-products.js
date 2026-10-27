/* ==========================================================================
   O’TOOSIN Farms Admin — Product list (admin-products.html only)
   --------------------------------------------------------------------------
   The cards are already in the page, so the catalogue is fully readable
   without JavaScript. This controller filters, sorts and counts those
   existing cards in place — no data fetching, no fake loading states and
   no persistence layer.

   Local demonstration records live in admin-products.html. Prices are
   Naira in each product's selling unit. When the store backend is connected,
   the same card markup can be produced by a template loop and this controller
   can keep filtering the rendered list until server-side filtering replaces it.
   ========================================================================== */
(function () {
  "use strict";

  var SORT_DEFAULT = "default";

  var list = document.getElementById("fd-prod-list");
  if (!list) {
    return;
  }

  var listWrap = document.getElementById("fd-prod-list-wrap");
  var count = document.getElementById("fd-prod-count");
  var empty = document.getElementById("fd-prod-empty");
  var clear = document.getElementById("fd-prod-clear");
  var resetEmpty = document.getElementById("fd-prod-reset-empty");
  var search = document.getElementById("fd-prod-search");
  var category = document.getElementById("fd-prod-cat");
  var productState = document.getElementById("fd-prod-state");
  var sort = document.getElementById("fd-prod-sort");

  var cards = Array.prototype.slice.call(
    list.querySelectorAll(".fd-prod-card")
  );
  var originalOrder = cards.slice();
  var paginated = list.getAttribute("data-paginated") === "1";
  var totalProducts =
    parseInt(list.getAttribute("data-total"), 10) || cards.length;

  var state = {
    q: "",
    category: "all",
    productState: "all",
    sort: SORT_DEFAULT
  };

  function value(card, name) {
    return String(card.getAttribute("data-" + name) || "");
  }

  function matches(card) {
    if (state.category !== "all") {
      var cardGroup = value(card, "category-group");
      if (cardGroup !== state.category) {
        return false;
      }
    }
    if (state.productState !== "all" && value(card, "state") !== state.productState) {
      return false;
    }
    if (state.q) {
      var haystack = (
        value(card, "name") +
        " " +
        value(card, "category") +
        " " +
        value(card, "category-group") +
        " " +
        value(card, "state")
      ).toLowerCase();
      if (haystack.indexOf(state.q) === -1) {
        return false;
      }
    }
    return true;
  }

  function sortCards(rows) {
    var out = rows.slice();
    if (state.sort === "name-asc") {
      out.sort(function (a, b) {
        return value(a, "name").localeCompare(value(b, "name"));
      });
    } else if (state.sort === "name-desc") {
      out.sort(function (a, b) {
        return value(b, "name").localeCompare(value(a, "name"));
      });
    } else if (state.sort === "price-asc") {
      out.sort(function (a, b) {
        return Number(value(a, "price")) - Number(value(b, "price"));
      });
    } else if (state.sort === "price-desc") {
      out.sort(function (a, b) {
        return Number(value(b, "price")) - Number(value(a, "price"));
      });
    } else {
      /* Catalogue order is the order of the static cards. */
      out.sort(function (a, b) {
        return originalOrder.indexOf(a) - originalOrder.indexOf(b);
      });
    }
    return out;
  }

  function isPristine() {
    return (
      state.q === "" &&
      state.category === "all" &&
      state.productState === "all" &&
      state.sort === SORT_DEFAULT
    );
  }

  function updateSummary() {
    if (paginated) {
      return;
    }
    var totals = { Fresh: 0, Frozen: 0, Fried: 0, Live: 0 };
    for (var i = 0; i < cards.length; i++) {
      var cardState = value(cards[i], "state");
      if (totals[cardState] !== undefined) {
        totals[cardState] += 1;
      }
    }
    var total = document.getElementById("fd-sum-total");
    var fresh = document.getElementById("fd-sum-fresh");
    var frozen = document.getElementById("fd-sum-frozen");
    var fried = document.getElementById("fd-sum-fried");
    var live = document.getElementById("fd-sum-live");
    if (total) {
      total.textContent = String(cards.length);
    }
    if (fresh) {
      fresh.textContent = String(totals.Fresh);
    }
    if (frozen) {
      frozen.textContent = String(totals.Frozen);
    }
    if (fried) {
      fried.textContent = String(totals.Fried);
    }
    if (live) {
      live.textContent = String(totals.Live);
    }
  }

  function apply() {
    var visible = cards.filter(matches);
    var ordered = sortCards(visible);

    for (var i = 0; i < cards.length; i++) {
      cards[i].hidden = true;
    }
    for (var j = 0; j < ordered.length; j++) {
      ordered[j].hidden = false;
      list.appendChild(ordered[j]);
    }

    if (count) {
      count.textContent = paginated
        ? "Showing " + ordered.length + " on this page · " +
          totalProducts + " products in total."
        : "Showing " + ordered.length + " of " + cards.length + " products.";
    }
    if (listWrap) {
      listWrap.hidden = ordered.length === 0;
    }
    if (empty) {
      empty.hidden = ordered.length !== 0;
    }
    if (clear) {
      clear.disabled = isPristine();
    }
  }

  function resetFilters(focusSearch) {
    state = {
      q: "",
      category: "all",
      productState: "all",
      sort: SORT_DEFAULT
    };
    if (search) {
      search.value = "";
    }
    if (category) {
      category.value = "all";
    }
    if (productState) {
      productState.value = "all";
    }
    if (sort) {
      sort.value = SORT_DEFAULT;
    }
    apply();
    if (focusSearch && search) {
      search.focus();
    }
  }

  /* Deep link from the Categories page: ?category=Pork sets the initial
     category filter. Unknown values are ignored so the page still opens
     on the full catalogue. */
  function applyUrlCategory() {
    var params = null;
    try {
      params = new URLSearchParams(window.location.search);
    } catch (e) {
      params = null;
    }
    if (!params) {
      return;
    }
    var raw = params.get("category") || "";
    if (!raw) {
      return;
    }
    var wanted = raw.replace(/-/g, " ").toLowerCase();
    var meatGroups = ["pork", "chicken", "turkey", "beef", "goat meat"];
    if (meatGroups.indexOf(wanted) !== -1) {
      wanted = "meats";
    }
    if (!category) {
      return;
    }
    for (var i = 0; i < category.options.length; i++) {
      var option = category.options[i];
      if (
        option.value !== "all" &&
        option.value.toLowerCase() === wanted
      ) {
        state.category = option.value;
        category.value = option.value;
        return;
      }
    }
  }

  applyUrlCategory();

  var debounce = null;

  if (search) {
    search.addEventListener("input", function () {
      window.clearTimeout(debounce);
      debounce = window.setTimeout(function () {
        state.q = search.value.trim().toLowerCase();
        apply();
      }, 120);
    });
    search.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && search.value) {
        search.value = "";
        state.q = "";
        apply();
      }
    });
  }

  if (category) {
    category.addEventListener("change", function () {
      state.category = category.value;
      apply();
    });
  }

  if (productState) {
    productState.addEventListener("change", function () {
      state.productState = productState.value;
      apply();
    });
  }

  if (sort) {
    sort.addEventListener("change", function () {
      state.sort = sort.value;
      apply();
    });
  }

  if (clear) {
    clear.addEventListener("click", function () {
      resetFilters(false);
    });
  }

  if (resetEmpty) {
    resetEmpty.addEventListener("click", function () {
      resetFilters(true);
    });
  }

  updateSummary();
  apply();

  window.OtoosinAdminProducts = {
    apply: apply,
    reset: resetFilters,
    matches: matches,
    sort: sortCards
  };
})();
