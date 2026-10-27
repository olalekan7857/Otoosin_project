/* ==========================================================================
   O’TOOSIN Farms Admin — Product Categories (admin-categories.html only)
   --------------------------------------------------------------------------
   The six category cards are already in the page, so the list is fully
   readable without JavaScript. This controller:
     1. Reads the current product catalogue (built-in records merged with
        products kept in this browser) and writes the real per-category and
        per-condition counts into the existing cards.
     2. Filters those cards by search text and category type.

   Product records keep their specific meat category (Pork, Chicken, …) while
   the category page groups them under the six storefront sections. Nothing is
   invented, nothing is saved here, and the order stays Meats, Fish,
   Live Animals, Eggs, Veggies, Fruits.
   ========================================================================== */
(function () {
  "use strict";

  var list = document.getElementById("fd-cat-list");
  if (!list) {
    return;
  }

  var listWrap = document.getElementById("fd-cat-list-wrap");
  var countEl = document.getElementById("fd-cat-count");
  var empty = document.getElementById("fd-cat-empty");
  var clearBtn = document.getElementById("fd-cat-clear");
  var resetEmpty = document.getElementById("fd-cat-reset-empty");
  var search = document.getElementById("fd-cat-search");
  var groupSelect = document.getElementById("fd-cat-group");

  var cards = Array.prototype.slice.call(
    list.querySelectorAll(".fd-cat-card")
  );

  var MEAT_CATEGORIES = ["Pork", "Chicken", "Turkey", "Beef", "Goat Meat", "Meats"];

  var state = {
    q: "",
    group: "all"
  };

  function readCatalog() {
    try {
      if (
        window.FreshDirectAdminProducts &&
        typeof window.FreshDirectAdminProducts.getCatalog === "function"
      ) {
        return window.FreshDirectAdminProducts.getCatalog() || {};
      }
    } catch (e) {
      /* Fall through to the static counts already in the markup. */
    }
    return null;
  }

  function cardValue(card, name) {
    return String(card.getAttribute("data-" + name) || "");
  }

  function setText(node, value) {
    if (node) {
      node.textContent = String(value);
    }
  }

  function mainCategory(entry) {
    var category = entry && entry.category ? String(entry.category) : "";
    if (MEAT_CATEGORIES.indexOf(category) !== -1) {
      return "Meats";
    }
    if (
      category === "Fish" ||
      category === "Live Animals" ||
      category === "Eggs" ||
      category === "Veggies" ||
      category === "Fruits"
    ) {
      return category;
    }
    return "";
  }

  function cardStates(card) {
    return cardValue(card, "states")
      .split(",")
      .map(function (item) {
        return item.replace(/^\s+|\s+$/g, "");
      })
      .filter(function (item) {
        return item;
      });
  }

  function applyCounts() {
    var catalog = readCatalog();
    if (!catalog) {
      return;
    }

    var totals = {};
    for (var i = 0; i < cards.length; i++) {
      var bucket = { total: 0 };
      var states = cardStates(cards[i]);
      for (var s = 0; s < states.length; s++) {
        bucket[states[s]] = 0;
      }
      totals[cardValue(cards[i], "category")] = bucket;
    }

    var ids = Object.keys(catalog);
    for (var j = 0; j < ids.length; j++) {
      var entry = catalog[ids[j]];
      var category = mainCategory(entry);
      if (!category || !totals[category]) {
        continue;
      }
      var bucketForEntry = totals[category];
      bucketForEntry.total += 1;
      if (Object.prototype.hasOwnProperty.call(bucketForEntry, entry.condition)) {
        bucketForEntry[entry.condition] += 1;
      }
    }

    var groupTotals = {};
    var grandTotal = 0;
    for (var k = 0; k < cards.length; k++) {
      var card = cards[k];
      var categoryName = cardValue(card, "category");
      var bucketForCard = totals[categoryName] || { total: 0 };
      setText(card.querySelector(".fd-cat-total"), bucketForCard.total);

      var stateNodes = card.querySelectorAll(".fd-cat-state");
      for (var n = 0; n < stateNodes.length; n++) {
        var stateName = stateNodes[n].getAttribute("data-state") || "";
        setText(stateNodes[n], bucketForCard[stateName] || 0);
      }

      grandTotal += bucketForCard.total;

      var group = cardValue(card, "group");
      groupTotals[group] = (groupTotals[group] || 0) + bucketForCard.total;
    }

    setText(document.getElementById("fd-cat-summary-categories"), cards.length);
    setText(document.getElementById("fd-cat-summary-total"), grandTotal);
    setText(document.getElementById("fd-cat-summary-meats"), groupTotals.Meat || 0);
    setText(document.getElementById("fd-cat-summary-fish"), groupTotals.Seafood || 0);
    setText(document.getElementById("fd-cat-summary-live"), groupTotals["Farm animals"] || 0);
    setText(document.getElementById("fd-cat-summary-produce"), groupTotals["Farm produce"] || 0);
  }

  function matches(card) {
    if (state.group !== "all" && cardValue(card, "group") !== state.group) {
      return false;
    }
    if (state.q) {
      var haystack = (
        cardValue(card, "category") +
        " " +
        cardValue(card, "slug") +
        " " +
        cardValue(card, "group") +
        " " +
        cardValue(card, "search")
      ).toLowerCase();
      if (haystack.indexOf(state.q) === -1) {
        return false;
      }
    }
    return true;
  }

  function isPristine() {
    return state.q === "" && state.group === "all";
  }

  function apply() {
    var visible = 0;
    for (var i = 0; i < cards.length; i++) {
      var show = matches(cards[i]);
      cards[i].hidden = !show;
      if (show) {
        visible += 1;
      }
    }
    if (countEl) {
      countEl.textContent =
        "Showing " + visible + " of " + cards.length + " categories.";
    }
    if (listWrap) {
      listWrap.hidden = visible === 0;
    }
    if (empty) {
      empty.hidden = visible !== 0;
    }
    if (clearBtn) {
      clearBtn.disabled = isPristine();
    }
  }

  function resetFilters(focusSearch) {
    state = { q: "", group: "all" };
    if (search) {
      search.value = "";
    }
    if (groupSelect) {
      groupSelect.value = "all";
    }
    apply();
    if (focusSearch && search) {
      search.focus();
    }
  }

  /* Deep link support keeps existing ?group= links working and maps the older
     meat groupings onto the current whole-farm category types. */
  function applyUrlGroup() {
    var params = null;
    try {
      params = new URLSearchParams(window.location.search);
    } catch (e) {
      params = null;
    }
    if (!params || !groupSelect) {
      return;
    }
    var raw = params.get("group") || params.get("type") || "";
    if (!raw) {
      return;
    }
    var wanted = raw.replace(/-/g, " ").toLowerCase();
    if (wanted === "red meat" || wanted === "poultry" || wanted === "meats") {
      wanted = "meat";
    }
    for (var i = 0; i < groupSelect.options.length; i++) {
      var option = groupSelect.options[i];
      if (option.value !== "all" && option.value.toLowerCase() === wanted) {
        state.group = option.value;
        groupSelect.value = option.value;
        return;
      }
    }
  }

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

  if (groupSelect) {
    groupSelect.addEventListener("change", function () {
      state.group = groupSelect.value;
      apply();
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      resetFilters(false);
    });
  }

  if (resetEmpty) {
    resetEmpty.addEventListener("click", function () {
      resetFilters(true);
    });
  }

  applyUrlGroup();
  applyCounts();
  apply();
})();
