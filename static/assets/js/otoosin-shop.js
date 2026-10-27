(function () {
  "use strict";

  function init() {
    var grid = document.getElementById("fd-shop-grid");
    if (!grid) {
      return;
    }

    var cards = Array.prototype.slice.call(
      grid.querySelectorAll("article.product-style1")
    );
    var toolbar = document.getElementById("oto-shop-toolbar");
    var viewButtons = toolbar
      ? toolbar.querySelectorAll("[data-shop-view]")
      : [];
    var viewKey = "freshdirect_shop_view";
    var search = document.getElementById("fd-shop-search");
    var typeSelect = document.getElementById("oto-shop-type");
    var conditionSelect = document.getElementById("oto-shop-condition");
    var sortSelect = document.getElementById("oto-shop-sort");
    var count = document.getElementById("oto-shop-count");
    var empty = document.getElementById("oto-shop-empty");
    var reset = document.getElementById("oto-shop-reset");
    var resetEmpty = document.getElementById("oto-shop-reset-empty");

    var state = {
      q: "",
      type: "all",
      condition: "all",
      sort: "featured",
    };

    var CATEGORY_SLUGS = {
      meats: "Meats",
      meat: "Meats",
      fish: "Fish",
      "live-animals": "Live Animals",
      liveanimals: "Live Animals",
      "live animals": "Live Animals",
      eggs: "Eggs",
      egg: "Eggs",
      veggies: "Veggies",
      vegetables: "Veggies",
      veg: "Veggies",
      fruits: "Fruits",
      fruit: "Fruits",
    };

    function categoryFromSlug(value) {
      var key = (value || "").trim().toLowerCase();
      return CATEGORY_SLUGS[key] || false;
    }

    function mainCategory(card) {
      var category = attr(card, "data-category");
      var condition = attr(card, "data-condition");
      if (category === "fish") {
        return "Fish";
      }
      if (category === "live animals" || condition === "live") {
        return "Live Animals";
      }
      if (category === "eggs") {
        return "Eggs";
      }
      if (category === "veggies") {
        return "Veggies";
      }
      if (category === "fruits") {
        return "Fruits";
      }
      return "Meats";
    }

    function attr(card, name) {
      return (card.getAttribute(name) || "").toLowerCase();
    }

    function cardText(card) {
      return (
        attr(card, "data-product-name") +
        " " +
        attr(card, "data-category") +
        " " +
        attr(card, "data-type") +
        " " +
        attr(card, "data-condition") +
        " " +
        attr(card, "data-group") +
        " " +
        card.textContent
      ).toLowerCase();
    }

    function matches(card) {
      if (state.q && cardText(card).indexOf(state.q) === -1) {
        return false;
      }
      if (state.type !== "all" && mainCategory(card) !== state.type) {
        return false;
      }
      if (
        state.condition !== "all" &&
        attr(card, "data-condition") !== state.condition.toLowerCase()
      ) {
        return false;
      }
      return true;
    }

    function orderOf(card) {
      return parseInt(card.getAttribute("data-order"), 10) || 0;
    }

    function priceOf(card) {
      return parseInt(card.getAttribute("data-price"), 10) || 0;
    }

    function nameOf(card) {
      return attr(card, "data-product-name");
    }

    function resultLabel(visible) {
      var scope = state.type !== "all" ? " in " + state.type : "";
      if (!visible) {
        return "No products match your filters";
      }
      if (visible === cards.length && state.type === "all") {
        return "Showing all " + cards.length + " products";
      }
      return "Showing " + visible + " of " + cards.length + " products" + scope;
    }

    function syncUrl() {
      if (!window.history || !window.history.replaceState) {
        return;
      }
      try {
        var params = new URLSearchParams(window.location.search);
        if (state.q) {
          params.set("q", state.q);
        } else {
          params.delete("q");
        }
        params.delete("type");
        if (state.type !== "all") {
          params.set("category", state.type);
        } else {
          params.delete("category");
        }
        if (state.condition !== "all") {
          params.set("state", state.condition.toLowerCase());
        } else {
          params.delete("state");
        }
        if (state.sort !== "featured") {
          params.set("sort", state.sort);
        } else {
          params.delete("sort");
        }
        var query = params.toString();
        window.history.replaceState(
          null,
          "",
          window.location.pathname +
            (query ? "?" + query : "") +
            window.location.hash
        );
      } catch (error) {
        /* URL state is optional. */
      }
    }

    function apply() {
      var visible = cards.filter(matches);

      if (state.sort === "price-asc") {
        visible.sort(function (a, b) {
          return priceOf(a) - priceOf(b);
        });
      } else if (state.sort === "price-desc") {
        visible.sort(function (a, b) {
          return priceOf(b) - priceOf(a);
        });
      } else if (state.sort === "name") {
        visible.sort(function (a, b) {
          return nameOf(a) < nameOf(b) ? -1 : nameOf(a) > nameOf(b) ? 1 : 0;
        });
      } else if (state.sort === "name-desc") {
        visible.sort(function (a, b) {
          return nameOf(a) > nameOf(b) ? -1 : nameOf(a) < nameOf(b) ? 1 : 0;
        });
      } else {
        visible.sort(function (a, b) {
          return orderOf(a) - orderOf(b);
        });
      }

      for (var i = 0; i < cards.length; i++) {
        cards[i].hidden = true;
        var col = cards[i].parentNode;
        if (col && col !== grid) {
          col.hidden = true;
          col.style.display = "none";
        } else {
          cards[i].style.display = "none";
        }
      }

      for (var j = 0; j < visible.length; j++) {
        var visibleCol = visible[j].parentNode;
        visible[j].hidden = false;
        if (visibleCol && visibleCol !== grid) {
          visibleCol.hidden = false;
          visibleCol.style.display = "";
        } else {
          visible[j].style.display = "";
        }
        if (visibleCol && visibleCol !== grid) {
          grid.appendChild(visibleCol);
        } else {
          grid.appendChild(visible[j]);
        }
      }

      if (count) {
        count.textContent = resultLabel(visible.length);
      }
      if (empty) {
        empty.hidden = visible.length > 0;
      }
      syncUrl();
    }

    function clearFilters(focusSearch) {
      state.q = "";
      state.type = "all";
      state.condition = "all";
      state.sort = "featured";
      if (search) {
        search.value = "";
      }
      if (typeSelect) {
        typeSelect.value = "all";
      }
      if (conditionSelect) {
        conditionSelect.value = "all";
      }
      if (sortSelect) {
        sortSelect.value = "featured";
      }
      apply();
      if (focusSearch && search) {
        search.focus();
      }
    }

    function hasOption(select, value) {
      if (!select) {
        return false;
      }
      for (var i = 0; i < select.options.length; i++) {
        if (select.options[i].value.toLowerCase() === value.toLowerCase()) {
          return select.options[i].value;
        }
      }
      return false;
    }

    function readQuery() {
      var params;
      try {
        params = new URLSearchParams(window.location.search);
      } catch (error) {
        return;
      }

      var q = params.get("q");
      if (q) {
        state.q = q.trim().toLowerCase();
        if (search) {
          search.value = q.trim();
        }
      }

      var category = params.get("category") || params.get("type");
      var categoryValue = category ? categoryFromSlug(category) : false;
      if (categoryValue && typeSelect) {
        typeSelect.value = categoryValue;
        state.type = categoryValue;
      }

      var condition = params.get("state");
      var conditionValue = condition
        ? hasOption(conditionSelect, condition)
        : false;
      if (conditionValue) {
        conditionSelect.value = conditionValue;
        state.condition = conditionValue;
      }

      var sort = params.get("sort");
      var sortValue = sort ? hasOption(sortSelect, sort) : false;
      if (sortValue) {
        sortSelect.value = sortValue;
        state.sort = sortValue;
      }
    }

    function focusSearchFromHash() {
      if (window.location.hash !== "#fd-shop-search" || !search) {
        return;
      }
      try {
        search.scrollIntoView({ block: "center" });
      } catch (error) {
        search.scrollIntoView();
      }
      search.focus({ preventScroll: true });
    }

    var debounce = null;
    if (search) {
      search.addEventListener("input", function () {
        window.clearTimeout(debounce);
        debounce = window.setTimeout(function () {
          state.q = search.value.trim().toLowerCase();
          apply();
        }, 150);
      });
    }

    if (typeSelect) {
      typeSelect.addEventListener("change", function () {
        state.type = typeSelect.value;
        apply();
      });
    }

    if (conditionSelect) {
      conditionSelect.addEventListener("change", function () {
        state.condition = conditionSelect.value;
        apply();
      });
    }

    if (sortSelect) {
      sortSelect.addEventListener("change", function () {
        state.sort = sortSelect.value;
        apply();
      });
    }

    if (reset) {
      reset.addEventListener("click", function () {
        clearFilters(true);
      });
    }

    if (resetEmpty) {
      resetEmpty.addEventListener("click", function () {
        clearFilters(true);
      });
    }

    if (search) {
      var searchLink = document.querySelector('a[href="#fd-shop-search"]');
      if (searchLink) {
        searchLink.addEventListener("click", function () {
          window.setTimeout(function () {
            search.focus({ preventScroll: true });
          }, 0);
        });
      }
    }

    function setView(view, persist) {
      if (view === "list") {
        grid.classList.add("is-list");
      } else {
        grid.classList.remove("is-list");
      }
      for (var i = 0; i < viewButtons.length; i++) {
        viewButtons[i].setAttribute(
          "aria-pressed",
          viewButtons[i].getAttribute("data-shop-view") === view
            ? "true"
            : "false"
        );
      }
      if (persist) {
        try {
          window.sessionStorage.setItem(viewKey, view);
        } catch (error) {
          /* private mode — view resets next visit */
        }
      }
    }

    if (viewButtons.length) {
      var savedView = null;
      try {
        savedView = window.sessionStorage.getItem(viewKey);
      } catch (error) {
        savedView = null;
      }
      setView(savedView === "list" ? "list" : "grid", false);
      if (toolbar) {
        toolbar.addEventListener("click", function (event) {
          var button = event.target.closest("[data-shop-view]");
          if (!button) {
            return;
          }
          setView(button.getAttribute("data-shop-view"), true);
        });
      }
    }

    readQuery();
    apply();
    focusSearchFromHash();

    window.addEventListener("hashchange", focusSearchFromHash);

    window.OtoosinShop = {
      state: state,
      apply: apply,
      reset: clearFilters,
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
