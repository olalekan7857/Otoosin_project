/* ==========================================================================
   O’TOOSIN Farms Admin — Product list sync
   --------------------------------------------------------------------------
   Runs before fd-admin-products.js. It applies products kept in the local
   seller store to the static cards and adds cards for newly created products,
   so the editor's save state and the Products page stay in step.
   The list controller then filters and counts the resulting cards normally.
   ========================================================================== */
(function () {
  "use strict";

  var list = document.getElementById("fd-prod-list");
  if (!list) {
    return;
  }

  var VALID_CATEGORIES = [
    "Pork", "Chicken", "Turkey", "Beef", "Goat Meat", "Fish",
    "Live Animals", "Eggs", "Veggies", "Fruits"
  ];
  var VALID_CONDITIONS = ["Fresh", "Frozen", "Fried", "Live"];
  var MEAT_CATEGORIES = ["Pork", "Chicken", "Turkey", "Beef", "Goat Meat"];
  var GROUPS = {
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

  function parentGroup(category) {
    return MEAT_CATEGORIES.indexOf(category) !== -1 ? "Meats" : category;
  }

  function categoryText(category) {
    var group = GROUPS[category] || "";
    var top = parentGroup(category);
    if (top === category) {
      return group ? category + " · " + group : category;
    }
    return "Meats · " + category + " · " + group;
  }

  function unitText(entry) {
    var basis = String(entry.priceUnit || entry.priceBasis || "").toLowerCase();
    if (basis.indexOf("chicken") !== -1) {
      return { suffix: "/ chicken", hidden: "Price per chicken: " };
    }
    if (basis.indexOf("crate") !== -1) {
      return { suffix: "/ crate", hidden: "Price per crate: " };
    }
    if (basis.indexOf("basket") !== -1) {
      return { suffix: "/ basket", hidden: "Price per basket: " };
    }
    return { suffix: "/ kg", hidden: "Price per kg: " };
  }

  function fmtNaira(n) {
    return "\u20A6" + Number(n).toLocaleString("en-NG");
  }

  function validEntry(entry) {
    if (!entry || typeof entry !== "object" || !entry.id || !entry.name) {
      return false;
    }
    if (VALID_CATEGORIES.indexOf(entry.category) === -1) {
      return false;
    }
    if (VALID_CONDITIONS.indexOf(entry.condition) === -1) {
      return false;
    }
    if (!Array.isArray(entry.variants) || !entry.variants.length) {
      return false;
    }
    if (!Array.isArray(entry.images) || !entry.images.length) {
      return false;
    }
    return true;
  }

  function priceOf(entry) {
    var variants = entry.variants || [];
    var price = variants[0] ? Number(variants[0].price) : 0;
    if (!isFinite(price) || price < 0) {
      price = 0;
    }
    return price;
  }

  function cardFor(id) {
    var cards = list.querySelectorAll(".fd-prod-card");
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].getAttribute("data-product-id") === id) {
        return cards[i];
      }
    }
    return null;
  }

  function editLink(entry) {
    var a = document.createElement("a");
    a.className = "fd-prod-btn";
    a.href = "admin-product-edit.html?id=" + encodeURIComponent(entry.id);
    a.setAttribute("aria-label", "Edit " + entry.name);
    a.innerHTML = '<i class="fas fa-pen" aria-hidden="true"></i>Edit';
    return a;
  }

  function ensureEdit(card, entry) {
    var actions = card.querySelector(".fd-prod-actions");
    if (!actions) {
      return;
    }
    var existing = actions.querySelector('a[href^="admin-product-edit.html"]');
    if (existing) {
      existing.href = "admin-product-edit.html?id=" + encodeURIComponent(entry.id);
      existing.setAttribute("aria-label", "Edit " + entry.name);
      return;
    }
    actions.appendChild(editLink(entry));
  }

  function isLocalEntry(id) {
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

  function updateCard(card, entry) {
    var price = priceOf(entry);
    var unitMeta = unitText(entry);
    var image = entry.images[0] || { src: "", alt: entry.name };

    card.setAttribute("data-name", entry.name);
    card.setAttribute("data-category", entry.category);
    card.setAttribute("data-category-group", parentGroup(entry.category));
    card.setAttribute("data-state", entry.condition);
    card.setAttribute("data-price", String(price));
    card.setAttribute("data-unit", unitMeta.suffix.replace("/ ", ""));

    var nameEl = card.querySelector(".fd-prod-name");
    if (nameEl) {
      nameEl.textContent = entry.name;
    }
    var catEl = card.querySelector(".fd-prod-cat");
    if (catEl) {
      catEl.textContent = categoryText(entry.category);
    }
    var stateEl = card.querySelector(".fd-prod-state");
    if (stateEl) {
      stateEl.textContent = entry.condition;
    }
    var img = card.querySelector(".fd-prod-thumb img");
    if (img && image.src) {
      img.setAttribute("src", image.src);
      img.setAttribute("alt", image.alt || entry.name);
      img.hidden = false;
    }
    var priceEl = card.querySelector(".fd-prod-price");
    if (priceEl) {
      priceEl.innerHTML = "";
      var hidden = document.createElement("span");
      hidden.className = "visually-hidden";
      hidden.textContent = unitMeta.hidden;
      priceEl.appendChild(hidden);
      priceEl.appendChild(document.createTextNode(fmtNaira(price) + " "));
      var unit = document.createElement("span");
      unit.className = "fd-prod-unit";
      unit.textContent = unitMeta.suffix;
      priceEl.appendChild(unit);
    }
    var view = card.querySelector('.fd-prod-actions a[href*="product-details.html"]');
    if (view) {
      if (isLocalEntry(entry.id)) {
        view.parentNode.removeChild(view);
      } else {
        view.setAttribute("href", "product-details.html?id=" + encodeURIComponent(entry.id));
        view.setAttribute("aria-label", "View " + entry.name + " on the storefront");
      }
    }
    ensureEdit(card, entry);
  }

  function createCard(entry, order) {
    var price = priceOf(entry);
    var unitMeta = unitText(entry);
    var image = entry.images[0] || { src: "", alt: entry.name };

    var li = document.createElement("li");
    li.className = "fd-prod-card";
    li.setAttribute("data-product-id", entry.id);
    li.setAttribute("data-name", entry.name);
    li.setAttribute("data-category", entry.category);
    li.setAttribute("data-category-group", parentGroup(entry.category));
    li.setAttribute("data-state", entry.condition);
    li.setAttribute("data-price", String(price));
    li.setAttribute("data-unit", unitMeta.suffix.replace("/ ", ""));
    li.setAttribute("data-order", String(order));

    var top = document.createElement("div");
    top.className = "fd-prod-card-top";

    var thumb = document.createElement("span");
    thumb.className = "fd-prod-thumb";
    var img = document.createElement("img");
    img.src = image.src;
    img.alt = image.alt || entry.name;
    img.width = 160;
    img.height = 120;
    img.loading = "lazy";
    img.decoding = "async";
    img.onerror = function () {
      img.hidden = true;
    };
    thumb.appendChild(img);
    top.appendChild(thumb);

    var idBlock = document.createElement("div");
    idBlock.className = "fd-prod-id-block";
    var name = document.createElement("h3");
    name.className = "fd-prod-name";
    name.textContent = entry.name;
    var cat = document.createElement("p");
    cat.className = "fd-prod-cat";
    cat.textContent = categoryText(entry.category);
    idBlock.appendChild(name);
    idBlock.appendChild(cat);
    top.appendChild(idBlock);

    var state = document.createElement("span");
    state.className = "fd-dash-pill fd-prod-state";
    state.textContent = entry.condition;
    top.appendChild(state);
    li.appendChild(top);

    var foot = document.createElement("div");
    foot.className = "fd-prod-card-foot";
    var priceEl = document.createElement("p");
    priceEl.className = "fd-prod-price";
    var hidden = document.createElement("span");
    hidden.className = "visually-hidden";
    hidden.textContent = unitMeta.hidden;
    priceEl.appendChild(hidden);
    priceEl.appendChild(document.createTextNode(fmtNaira(price) + " "));
    var unit = document.createElement("span");
    unit.className = "fd-prod-unit";
    unit.textContent = unitMeta.suffix;
    priceEl.appendChild(unit);
    foot.appendChild(priceEl);

    var actions = document.createElement("div");
    actions.className = "fd-prod-actions";
    actions.appendChild(editLink(entry));
    foot.appendChild(actions);
    li.appendChild(foot);

    return li;
  }

  var local = {};
  try {
    if (window.FreshDirectAdminStore && window.FreshDirectAdminStore.getLocal) {
      local = window.FreshDirectAdminStore.getLocal() || {};
    }
  } catch (e) {
    local = {};
  }

  var ids = Object.keys(local);
  var maxOrder = 0;
  var existingCards = list.querySelectorAll(".fd-prod-card");
  for (var i = 0; i < existingCards.length; i++) {
    var order = Number(existingCards[i].getAttribute("data-order")) || 0;
    if (order > maxOrder) {
      maxOrder = order;
    }
  }

  for (var j = 0; j < ids.length; j++) {
    var entry = local[ids[j]];
    if (!validEntry(entry)) {
      continue;
    }
    var card = cardFor(entry.id);
    if (card) {
      updateCard(card, entry);
    } else {
      maxOrder += 1;
      list.insertBefore(createCard(entry, maxOrder), list.firstChild);
    }
  }

  /* Edit stays reachable for every built-in card, even before any edits. */
  var allCards = list.querySelectorAll(".fd-prod-card");
  for (var k = 0; k < allCards.length; k++) {
    var id = allCards[k].getAttribute("data-product-id");
    var name = allCards[k].getAttribute("data-name") || "product";
    if (id) {
      ensureEdit(allCards[k], { id: id, name: name });
    }
  }
})();
