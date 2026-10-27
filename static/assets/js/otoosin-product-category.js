(function () {
  "use strict";

  var CATEGORIES = {
    all: {
      label: "All Products",
      title: "Shop All Products",
      kicker: "Product categories",
      lead:
        "Browse meats, fish, live animals, eggs, veggies and fruits by category. Each product shows its unit and condition where it applies, then goes straight into your cart.",
      image: "assets/img/categorie/otoosin-farms.png",
      alt: "O\u2019TOOSIN Farms produce and meats",
      group: "Meats \u00b7 Fish \u00b7 Live Animals \u00b7 Eggs \u00b7 Veggies \u00b7 Fruits",
      unit: "Units vary by product",
    },
    Meats: {
      label: "Meats",
      title: "Shop Meats",
      kicker: "Meat category",
      lead:
        "Browse pork, chicken, turkey, beef and goat meat in one place. Fresh, frozen and fried cuts are priced by the kilogram and ready to add to your cart.",
      image: "assets/img/hero/oto-hero-meat-sm.jpg",
      alt: "Fresh meat selection",
      group: "Pork \u00b7 Chicken \u00b7 Turkey \u00b7 Beef \u00b7 Goat Meat",
      unit: "Priced per kilogram",
    },
    Pork: {
      label: "Pork",
      title: "Shop Pork",
      kicker: "Pork category",
      lead:
        "Fresh and frozen pork cuts, prepared and priced by the kilogram. Choose a cut, add your weight to the cart, and check out when you are ready.",
      image: "assets/img/categorie/pork-meat.png",
      alt: "Fresh pork chops",
      group: "Red meat",
      unit: "Priced per kilogram",
    },
    Chicken: {
      label: "Chicken",
      title: "Shop Chicken",
      kicker: "Chicken category",
      lead:
        "From whole chickens to wings and drumsticks, browse fresh and frozen chicken by the kilogram. Every listing shows the condition before you add it to the cart.",
      image: "assets/img/categorie/chicken-meat.png",
      alt: "Whole fresh chicken",
      group: "Poultry",
      unit: "Priced per kilogram",
    },
    Turkey: {
      label: "Turkey",
      title: "Shop Turkey",
      kicker: "Turkey category",
      lead:
        "Lean turkey breast, prepared for roasting or slicing and sold by the kilogram. Add the weight you need directly from the product card.",
      image: "assets/img/categorie/turkey-meat.png",
      alt: "Fresh turkey breast",
      group: "Poultry",
      unit: "Priced per kilogram",
    },
    Beef: {
      label: "Beef",
      title: "Shop Beef",
      kicker: "Beef category",
      lead:
        "Browse fresh steak and frozen brisket, both priced per kilogram. Choose the cut that suits your cooking and add it to your cart.",
      image: "assets/img/categorie/beef-meat.png",
      alt: "Fresh marbled beef steak",
      group: "Red meat",
      unit: "Priced per kilogram",
    },
    "Goat Meat": {
      label: "Goat Meat",
      title: "Shop Goat Meat",
      kicker: "Goat Meat category",
      lead:
        "Fresh goat meat for stews and soups, plus fried goat meat with a deeper savoury flavour. Every option is sold by the kilogram.",
      image: "assets/img/categorie/goat-meat.png",
      alt: "Fresh cubed goat meat",
      group: "Red meat",
      unit: "Priced per kilogram",
    },
    Fish: {
      label: "Fish",
      title: "Shop Fish",
      kicker: "Fish category",
      lead:
        "Fresh, frozen and fried fish, cleaned and sold by the kilogram. Browse catfish and tilapia, then add the amount your kitchen needs.",
      image: "assets/img/categorie/fish-meat.png",
      alt: "Fresh whole catfish",
      group: "Seafood",
      unit: "Priced per kilogram",
    },
    "Live Animals": {
      label: "Live Animals",
      title: "Shop Live Animals",
      kicker: "Live Animals category",
      lead:
        "Healthy live chickens and farm animals, priced per chicken or animal. Choose what you need and add it to your cart for collection or arranged delivery.",
      image: "assets/img/categorie/otoosin-live-animals.png",
      alt: "Live chickens, goats, a cow, a sheep and a pig on the farm",
      group: "Farm animals",
      unit: "Priced per chicken or animal",
    },
    Eggs: {
      label: "Eggs",
      title: "Shop Eggs",
      kicker: "Eggs category",
      lead:
        "Fresh eggs from the farm, packed by the crate. Browse the current selection and add a crate to your cart.",
      image: "assets/img/categorie/otoosin-eggs.png",
      alt: "Fresh brown farm eggs in a basket",
      group: "Farm produce",
      unit: "Priced per crate",
    },
    Veggies: {
      label: "Veggies",
      title: "Shop Veggies",
      kicker: "Veggies category",
      lead:
        "Farm-fresh vegetables, sorted and packed by the basket. Browse what is available and add your selection to the cart.",
      image: "assets/img/categorie/otoosin-veggies.png",
      alt: "Fresh farm vegetables including tomatoes, carrots, peppers and greens",
      group: "Farm produce",
      unit: "Priced per basket",
    },
    Fruits: {
      label: "Fruits",
      title: "Shop Fruits",
      kicker: "Fruits category",
      lead:
        "Seasonal fruit from the farm, hand-picked and packed by the basket. Browse the selection and add your fruit to the cart.",
      image: "assets/img/categorie/otoosin-fruits.png",
      alt: "Fresh farm fruits including oranges, bananas, pineapple and mango",
      group: "Farm produce",
      unit: "Priced per basket",
    },
  };

  var SLUGS = {
    all: "all",
    meats: "Meats",
    meat: "Meats",
    pork: "Pork",
    chicken: "Chicken",
    turkey: "Turkey",
    beef: "Beef",
    "goat-meat": "Goat Meat",
    "goat meat": "Goat Meat",
    goat: "Goat Meat",
    fish: "Fish",
    "live-animals": "Live Animals",
    liveanimals: "Live Animals",
    eggs: "Eggs",
    egg: "Eggs",
    veggies: "Veggies",
    vegetables: "Veggies",
    veg: "Veggies",
    fruits: "Fruits",
    fruit: "Fruits",
  };

  function categoryFromSlug(raw) {
    var value = String(raw || "")
      .trim()
      .toLowerCase()
      .replace(/_/g, "-")
      .replace(/\s+/g, "-");
    return SLUGS[value] || "all";
  }

  function init() {
    var grid = document.getElementById("fd-shop-grid");
    if (!grid) {
      return;
    }

    var cards = Array.prototype.slice.call(
      grid.querySelectorAll("article.product-style1[data-product-id]")
    );
    var toolbar = document.getElementById("oto-category-toolbar");
    var search = document.getElementById("fd-shop-search");
    var stateSelect = document.getElementById("oto-category-state");
    var sortSelect = document.getElementById("oto-category-sort");
    var count = document.getElementById("oto-category-count");
    var empty = document.getElementById("oto-category-empty");
    var emptyTitle = document.getElementById("oto-category-empty-title");
    var reset = document.getElementById("oto-category-reset");
    var resetEmpty = document.getElementById("oto-category-reset-empty");
    var viewButtons = toolbar
      ? toolbar.querySelectorAll("[data-category-view]")
      : [];
    var viewKey = "freshdirect_category_view";

    var heading = document.getElementById("oto-category-heading");
    var crumb = document.getElementById("oto-category-crumb");
    var kicker = document.getElementById("oto-category-kicker");
    var lead = document.getElementById("oto-category-lead");
    var image = document.getElementById("oto-category-image");
    var caption = document.getElementById("oto-category-caption");
    var countLabel = document.getElementById("oto-category-count-label");
    var unitLabel = document.getElementById("oto-category-unit-label");
    var metaDescription = document.querySelector('meta[name="description"]');
    var categoryLinks = document.querySelectorAll("[data-category-link]");
    var categoryCounts = document.querySelectorAll("[data-category-count]");

    var state = {
      category: "all",
      q: "",
      condition: "all",
      sort: "featured",
    };

    function attr(card, name) {
      return (card.getAttribute(name) || "").toLowerCase();
    }

    function cardCategory(card) {
      var category = attr(card, "data-category");
      var slug = categoryFromSlug(category);
      if (slug !== "all") {
        return slug;
      }
      return "Meats";
    }

    function isMeatCategory(category) {
      return (
        category === "Pork" ||
        category === "Chicken" ||
        category === "Turkey" ||
        category === "Beef" ||
        category === "Goat Meat" ||
        category === "Meats"
      );
    }

    function matchesCategory(card, category) {
      if (category === "all") {
        return true;
      }
      var cardCategoryName = cardCategory(card);
      if (category === "Meats") {
        return isMeatCategory(cardCategoryName);
      }
      return cardCategoryName === category;
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

    function cardsForCategory() {
      if (state.category === "all") {
        return cards.slice();
      }
      return cards.filter(function (card) {
        return matchesCategory(card, state.category);
      });
    }

    function matches(card) {
      if (state.q && cardText(card).indexOf(state.q) === -1) {
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

    function priceOf(card) {
      return parseInt(card.getAttribute("data-price"), 10) || 0;
    }

    function nameOf(card) {
      return attr(card, "data-product-name");
    }

    function orderOf(card) {
      return parseInt(card.getAttribute("data-order"), 10) || 0;
    }

    function categoryCards() {
      return cardsForCategory();
    }

    function setChrome() {
      var category = CATEGORIES[state.category];
      if (heading) {
        heading.textContent = category.title;
      }
      if (crumb) {
        crumb.textContent = category.label;
      }
      if (kicker) {
        kicker.textContent = category.kicker;
      }
      if (lead) {
        lead.textContent = category.lead;
      }
      if (image) {
        image.style.setProperty(
          "--oto-category-image",
          'url("../' + category.image.replace(/^assets\//, "") + '")'
        );
        image.setAttribute("aria-label", category.alt);
      }
      if (caption) {
        caption.textContent = category.group;
      }
      if (unitLabel) {
        unitLabel.textContent = category.unit;
      }
      document.title =
        (state.category === "all"
          ? "Shop by Product Category"
          : category.title) + " | O\u2019TOOSIN Farms";
      if (metaDescription) {
        metaDescription.setAttribute("content", category.lead);
      }
      for (var i = 0; i < categoryLinks.length; i++) {
        var link = categoryLinks[i];
        var isActive =
          categoryFromSlug(link.getAttribute("data-category-link")) ===
          state.category;
        link.classList.toggle("is-active", isActive);
        if (isActive) {
          link.setAttribute("aria-current", "page");
        } else {
          link.removeAttribute("aria-current");
        }
      }
      for (var j = 0; j < categoryCounts.length; j++) {
        var countCategory = categoryFromSlug(
          categoryCounts[j].getAttribute("data-category-count")
        );
        var total =
          countCategory === "all"
            ? cards.length
            : cards.filter(function (card) {
                return matchesCategory(card, countCategory);
              }).length;
        categoryCounts[j].textContent = String(total);
      }
    }

    function stateOptions() {
      var available = {};
      var scoped = categoryCards();
      for (var i = 0; i < scoped.length; i++) {
        available[attr(scoped[i], "data-condition")] = true;
      }
      if (!stateSelect) {
        return;
      }
      for (var j = 0; j < stateSelect.options.length; j++) {
        var option = stateSelect.options[j];
        if (option.value === "all") {
          continue;
        }
        var isAvailable = !!available[option.value.toLowerCase()];
        option.hidden = !isAvailable;
        option.disabled = !isAvailable;
        if (!isAvailable && state.condition === option.value) {
          state.condition = "all";
          stateSelect.value = "all";
        }
      }
    }

    function resultLabel(visible, total) {
      var label = CATEGORIES[state.category].label;
      if (!visible) {
        return "No products match your filters";
      }
      if (state.category === "all" && visible === total) {
        return "Showing all " + total + " products";
      }
      if (visible === total) {
        return "Showing all " + total + " in " + label;
      }
      return "Showing " + visible + " of " + total + " in " + label;
    }

    function slugForCategory(category) {
      if (category === "Goat Meat") {
        return "Goat-Meat";
      }
      if (category === "Live Animals") {
        return "Live-Animals";
      }
      return category;
    }

    function syncUrl() {
      if (!window.history || !window.history.replaceState) {
        return;
      }
      try {
        var params = new URLSearchParams(window.location.search);
        if (state.category !== "all") {
          params.set("category", slugForCategory(state.category));
        } else {
          params.delete("category");
        }
        if (state.q) {
          params.set("q", state.q);
        } else {
          params.delete("q");
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
      var scoped = categoryCards();
      var visible = scoped.filter(matches);

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
        count.textContent = resultLabel(visible.length, scoped.length);
      }
      if (countLabel) {
        countLabel.textContent =
          scoped.length + (scoped.length === 1 ? " product" : " products");
      }
      if (empty) {
        empty.hidden = visible.length > 0;
      }
      if (emptyTitle) {
        emptyTitle.textContent =
          state.category === "all"
            ? "No products found"
            : "No products found in " + CATEGORIES[state.category].label;
      }
      syncUrl();
    }

    function clearFilters(focusSearch) {
      state.q = "";
      state.condition = "all";
      state.sort = "featured";
      if (search) {
        search.value = "";
      }
      if (stateSelect) {
        stateSelect.value = "all";
      }
      if (sortSelect) {
        sortSelect.value = "featured";
      }
      apply();
      if (focusSearch && search) {
        search.focus();
      }
    }

    function readQuery() {
      var params;
      try {
        params = new URLSearchParams(window.location.search);
      } catch (error) {
        return;
      }

      state.category = categoryFromSlug(params.get("category"));

      var q = params.get("q");
      if (q) {
        state.q = q.trim().toLowerCase();
        if (search) {
          search.value = q.trim();
        }
      }

      var conditions = {
        fresh: "Fresh",
        frozen: "Frozen",
        fried: "Fried",
        live: "Live",
      };
      var requestedCondition =
        conditions[(params.get("state") || "").toLowerCase()];
      if (requestedCondition && stateSelect) {
        state.condition = requestedCondition;
        stateSelect.value = requestedCondition;
      }

      var sorts = {
        featured: "featured",
        "price-asc": "price-asc",
        "price-desc": "price-desc",
        name: "name",
        "name-desc": "name-desc",
      };
      var requestedSort = sorts[params.get("sort") || ""];
      if (requestedSort && sortSelect) {
        state.sort = requestedSort;
        sortSelect.value = requestedSort;
      }
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

    if (stateSelect) {
      stateSelect.addEventListener("change", function () {
        state.condition = stateSelect.value;
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
          viewButtons[i].getAttribute("data-category-view") === view
            ? "true"
            : "false"
        );
      }
      if (persist) {
        try {
          window.sessionStorage.setItem(viewKey, view);
        } catch (error) {
          /* private mode — the view resets on the next visit */
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
          var button = event.target.closest("[data-category-view]");
          if (!button) {
            return;
          }
          setView(button.getAttribute("data-category-view"), true);
        });
      }
    }

    readQuery();
    setChrome();
    stateOptions();
    apply();

    window.OtoosinCategory = {
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
