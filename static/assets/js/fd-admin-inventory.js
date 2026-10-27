/* ==========================================================================
   O’TOOSIN Farms Admin — Inventory list (admin-inventory.html only)
   --------------------------------------------------------------------------
   Reads the SAME product catalogue the Products page, Dashboard and editor
   use (window.FreshDirectAdminProducts), so nothing is duplicated or can
   drift out of sync. The catalogue stores an availability status per
   product ("in", "limited", "out"); this page displays that status and
   filters/sorts it across all six farm categories. No stock quantity, cost,
   batch or supplier data exists in the current project, so none is shown or
   invented here.

   Vanilla JS, no dependencies. Admin-scoped: never touches the customer
   cart store or fresh-direct.js.
   ========================================================================== */
(function () {
  "use strict";

  var SORT_DEFAULT = "availability";

  var list = document.getElementById("fd-inv-list");
  if (!list) {
    return;
  }

  var cardsHost = document.getElementById("fd-inv-cards");
  var listWrap = document.getElementById("fd-inv-list-wrap");
  var countEl = document.getElementById("fd-inv-count");
  var emptyAll = document.getElementById("fd-inv-empty-all");
  var emptyFiltered = document.getElementById("fd-inv-empty-filtered");
  var clearBtn = document.getElementById("fd-inv-clear");
  var resetEmpty = document.getElementById("fd-inv-reset-empty");
  var errorBox = document.getElementById("fd-inv-error");
  var content = document.getElementById("fd-inv-content");
  var retry = document.getElementById("fd-inv-retry");
  var search = document.getElementById("fd-inv-search");
  var category = document.getElementById("fd-inv-category");
  var productState = document.getElementById("fd-inv-state");
  var availability = document.getElementById("fd-inv-availability");
  var sort = document.getElementById("fd-inv-sort");

  var CATEGORY_GROUP = {
    "Pork": "Red meat",
    "Chicken": "Poultry",
    "Turkey": "Poultry",
    "Beef": "Red meat",
    "Goat Meat": "Red meat",
    "Fish": "Seafood",
    "Live Animals": "Farm animals",
    "Eggs": "Farm produce",
    "Veggies": "Farm produce",
    "Fruits": "Farm produce"
  };
  var MEAT_CATEGORIES = ["Pork", "Chicken", "Turkey", "Beef", "Goat Meat", "Meats"];
  var CATEGORY_ORDER = ["Meats", "Fish", "Live Animals", "Eggs", "Veggies", "Fruits"];
  var CATEGORY_RANK = {};
  for (var orderIndex = 0; orderIndex < CATEGORY_ORDER.length; orderIndex++) {
    CATEGORY_RANK[CATEGORY_ORDER[orderIndex]] = orderIndex;
  }

  var state = {
    q: "",
    category: "all",
    productState: "all",
    availability: "all",
    sort: SORT_DEFAULT
  };

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[c];
    });
  }

  function mainCategory(category) {
    return MEAT_CATEGORIES.indexOf(category) !== -1 ? "Meats" : category;
  }

  function categoryLabel(row) {
    if (row.mainCategory === "Meats") {
      return row.group
        ? "Meats · " + row.category + " · " + row.group
        : "Meats · " + row.category;
    }
    return row.group ? row.category + " · " + row.group : row.category;
  }

  function unitLabel(entry) {
    var unit = String(entry.priceUnit || "").replace(/^\s+|\s+$/g, "");
    if (unit) {
      return unit;
    }
    var basis = String(entry.priceBasis || "").replace(/^\s+|\s+$/g, "");
    if (basis) {
      return basis;
    }
    var variant = entry.variants && entry.variants[0];
    var label = variant && variant.label ? String(variant.label) : "";
    if (label.indexOf("kg") !== -1) {
      return "per kg";
    }
    if (/crate/i.test(label)) {
      return "per crate";
    }
    if (/basket/i.test(label)) {
      return "per basket";
    }
    if (/chicken/i.test(label)) {
      return "per chicken";
    }
    return "—";
  }

  function availabilityMeta(status) {
    if (status === "out" || status === "draft" || status === "unavailable") {
      return { key: "out", label: "Out of Stock", tone: "is-bad", rank: 2 };
    }
    if (status === "limited") {
      return { key: "limited", label: "Limited", tone: "is-warn", rank: 1 };
    }
    return { key: "available", label: "Available", tone: "is-ok", rank: 0 };
  }

  function readCatalog() {
    try {
      if (
        window.FreshDirectAdminProducts &&
        typeof window.FreshDirectAdminProducts.getCatalog === "function"
      ) {
        return window.FreshDirectAdminProducts.getCatalog() || {};
      }
    } catch (e) {
      return null;
    }
    return null;
  }

  function toRows(catalog) {
    var ids = Object.keys(catalog);
    var rows = [];
    for (var i = 0; i < ids.length; i++) {
      var entry = catalog[ids[i]];
      if (!entry || typeof entry !== "object") {
        continue;
      }
      var name = String(entry.name || entry.id || "").trim();
      if (!name) {
        continue;
      }
      var categoryName = entry.category || "Uncategorised";
      var image = (entry.images && entry.images[0]) || { src: "", alt: "" };
      rows.push({
        id: String(entry.id || ids[i]),
        name: name,
        category: categoryName,
        mainCategory: mainCategory(categoryName),
        group: entry.group || CATEGORY_GROUP[categoryName] || "",
        condition: entry.condition || "",
        status: entry.status || "in",
        unit: unitLabel(entry),
        imageSrc: image.src || "",
        imageAlt: image.alt || name
      });
    }
    return rows;
  }

  function matches(row) {
    if (state.category !== "all" && row.mainCategory !== state.category) {
      return false;
    }
    if (state.productState !== "all" && row.condition !== state.productState) {
      return false;
    }
    if (state.availability !== "all") {
      if (availabilityMeta(row.status).key !== state.availability) {
        return false;
      }
    }
    if (state.q) {
      var haystack = (
        row.name +
        " " +
        row.id +
        " " +
        row.category +
        " " +
        row.mainCategory +
        " " +
        row.group +
        " " +
        row.condition +
        " " +
        row.unit
      ).toLowerCase();
      if (haystack.indexOf(state.q) === -1) {
        return false;
      }
    }
    return true;
  }

  function byName(a, b) {
    return a.name.localeCompare(b.name, "en", { sensitivity: "base" });
  }

  function sortRows(rows) {
    var out = rows.slice();
    if (state.sort === "name-asc") {
      out.sort(byName);
    } else if (state.sort === "name-desc") {
      out.sort(function (a, b) {
        return byName(b, a);
      });
    } else if (state.sort === "category") {
      out.sort(function (a, b) {
        var aRank = CATEGORY_RANK[a.mainCategory];
        var bRank = CATEGORY_RANK[b.mainCategory];
        if (aRank === undefined) {
          aRank = CATEGORY_ORDER.length;
        }
        if (bRank === undefined) {
          bRank = CATEGORY_ORDER.length;
        }
        if (aRank !== bRank) {
          return aRank - bRank;
        }
        var c = a.category.localeCompare(b.category, "en", { sensitivity: "base" });
        return c !== 0 ? c : byName(a, b);
      });
    } else {
      /* Unavailable first, then limited, then available; ties by name. */
      out.sort(function (a, b) {
        var diff =
          availabilityMeta(b.status).rank - availabilityMeta(a.status).rank;
        return diff !== 0 ? diff : byName(a, b);
      });
    }
    return out;
  }

  function renderCards(rows) {
    if (!cardsHost) {
      return;
    }
    var available = 0;
    var limited = 0;
    var out = 0;
    for (var i = 0; i < rows.length; i++) {
      var key = availabilityMeta(rows[i].status).key;
      if (key === "out") {
        out += 1;
      } else if (key === "limited") {
        limited += 1;
      } else {
        available += 1;
      }
    }
    var cards = [
      {
        icon: "fas fa-box",
        label: "Total products",
        value: rows.length,
        context: "Product lines across all six categories."
      },
      {
        icon: "fas fa-check-circle",
        label: "Available",
        value: available,
        context: "Can be ordered today."
      },
      {
        icon: "fas fa-exclamation-circle",
        label: "Limited",
        value: limited,
        context: "Marked with limited availability."
      },
      {
        icon: "fas fa-times-circle",
        label: "Out of Stock",
        value: out,
        context: "Unavailable until restocked."
      }
    ];
    var html = "";
    for (var j = 0; j < cards.length; j++) {
      html +=
        '<li class="fd-dash-card">' +
        '<span class="fd-dash-card-icon" aria-hidden="true"><i class="' +
        cards[j].icon +
        '"></i></span>' +
        '<span class="fd-dash-card-label">' +
        esc(cards[j].label) +
        "</span>" +
        '<span class="fd-dash-card-value">' +
        esc(cards[j].value) +
        "</span>" +
        '<span class="fd-dash-card-context">' +
        esc(cards[j].context) +
        "</span>" +
        "</li>";
    }
    cardsHost.innerHTML = html;
  }

  function isLocalProduct(id) {
    try {
      return !!(
        window.FreshDirectAdminStore &&
        window.FreshDirectAdminStore.isLocal &&
        window.FreshDirectAdminStore.isLocal(id)
      );
    } catch (e) {
      return false;
    }
  }

  function renderProducts(rows) {
    var html = "";
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var meta = availabilityMeta(row.status);
      var editHref =
        "admin-product-edit.html?id=" + encodeURIComponent(row.id);
      var viewHref =
        "product-details.html?id=" + encodeURIComponent(row.id);
      var viewAction = isLocalProduct(row.id)
        ? ""
        : '<a class="fd-prod-btn" href="' +
          esc(viewHref) +
          '" target="_blank" rel="noopener" aria-label="View ' +
          esc(row.name) +
          ' on the storefront"><i class="far fa-eye" aria-hidden="true"></i>View</a>';
      var thumb = row.imageSrc
        ? '<img src="' +
          esc(row.imageSrc) +
          '" alt="" width="144" height="144" loading="lazy" decoding="async" onerror="this.hidden=true">'
        : '<i class="fas fa-box" aria-hidden="true"></i>';
      html +=
        '<li class="fd-cat-card">' +
        '<div class="fd-cat-card-top">' +
        '<span class="fd-cat-thumb">' +
        thumb +
        "</span>" +
        '<div class="fd-cat-id">' +
        '<h3 class="fd-cat-name">' +
        esc(row.name) +
        "</h3>" +
        '<p class="fd-cat-group">' +
        esc(row.group || row.mainCategory) +
        "</p>" +
        "</div>" +
        "</div>" +
        '<p class="fd-cat-desc">' +
        esc(categoryLabel(row)) +
        ' &middot; Catalogue ID: <code class="fd-inv-code">' +
        esc(row.id) +
        "</code></p>" +
        '<ul class="fd-cat-stats" aria-label="' +
        esc(row.name) +
        ' inventory details">' +
        "<li><span class=\"fd-cat-stat-label\">Condition</span>" +
        '<span class="fd-cat-stat-value">' +
        esc(row.condition || "—") +
        "</span></li>" +
        '<li><span class="fd-cat-stat-label">Unit</span>' +
        '<span class="fd-cat-stat-value">' +
        esc(row.unit) +
        "</span></li>" +
        '<li><span class="fd-cat-stat-label">Availability</span>' +
        '<span class="fd-cat-stat-value fd-inv-status ' +
        esc(meta.tone) +
        '">' +
        esc(meta.label) +
        "</span></li>" +
        "</ul>" +
        '<div class="fd-cat-actions">' +
        '<a class="fd-prod-btn" href="' +
        esc(editHref) +
        '" aria-label="Edit ' +
        esc(row.name) +
        '"><i class="fas fa-pen" aria-hidden="true"></i>Edit</a>' +
        viewAction +
        "</div>" +
        "</li>";
    }
    list.innerHTML = html;
  }

  function isPristine() {
    return (
      state.q === "" &&
      state.category === "all" &&
      state.productState === "all" &&
      state.availability === "all" &&
      state.sort === SORT_DEFAULT
    );
  }

  function resetFilters(focusSearch) {
    state = {
      q: "",
      category: "all",
      productState: "all",
      availability: "all",
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
    if (availability) {
      availability.value = "all";
    }
    if (sort) {
      sort.value = SORT_DEFAULT;
    }
    apply();
    if (focusSearch && search) {
      search.focus();
    }
  }

  var allRows = [];

  function apply() {
    var visible = sortRows(allRows.filter(matches));

    if (countEl) {
      countEl.textContent =
        "Showing " + visible.length + " of " + allRows.length + " products.";
    }
    if (listWrap) {
      listWrap.hidden = visible.length === 0;
    }
    if (emptyAll) {
      emptyAll.hidden = !(allRows.length === 0);
    }
    if (emptyFiltered) {
      emptyFiltered.hidden = !(allRows.length > 0 && visible.length === 0);
    }
    if (clearBtn) {
      clearBtn.disabled = isPristine();
    }
    renderProducts(visible);
  }

  function load() {
    var catalog = readCatalog();
    if (!catalog || !Object.keys(catalog).length) {
      if (errorBox) {
        errorBox.hidden = false;
      }
      if (content) {
        content.hidden = true;
      }
      return false;
    }
    allRows = toRows(catalog);
    if (errorBox) {
      errorBox.hidden = true;
    }
    if (content) {
      content.hidden = false;
    }
    renderCards(allRows);
    apply();
    return true;
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

  if (availability) {
    availability.addEventListener("change", function () {
      state.availability = availability.value;
      apply();
    });
  }

  if (sort) {
    sort.addEventListener("change", function () {
      state.sort = sort.value;
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

  if (retry) {
    retry.addEventListener("click", function () {
      load();
    });
  }

  load();
})();
