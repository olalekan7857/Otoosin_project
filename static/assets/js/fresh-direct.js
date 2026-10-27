/* ==========================================================================
   Harvest Castle — single configuration + small enhancements (Stage 1)
   --------------------------------------------------------------------------
   SINGLE SOURCE OF TRUTH for values the backend will own later:
     FRESH_DIRECT.whatsappNumber  -> future Django setting WHATSAPP_NUMBER
     FRESH_DIRECT.currency        -> display-only until backend pricing lands
     FRESH_DIRECT.shopUrl         -> shop page target used by CTAs
   Do NOT hardcode the WhatsApp number in markup. Markup carries
   `data-whatsapp="<mode>"` (+ optional data-product / data-qty) and this
   file builds the wa.me link from the config below.
   ========================================================================== */
(function () {
  "use strict";

  var FRESH_DIRECT = {
    // Business WhatsApp number (country code + number, digits only).
    // Single source of truth — mirrors the future Django setting
    // WHATSAPP_NUMBER. Every WhatsApp entry point site-wide follows it.
    whatsappNumber: "2349011058873",
    defaultMessage:
      "Hello O'Toosin Farms! I would like to place an order for meat.",
    currency: "NGN",
    shopUrl: "product.html",
  };

  window.FRESH_DIRECT = FRESH_DIRECT;

  var FD_ROUTES = window.FD_ROUTES || {
    home: "index.html",
    shop: "product.html",
    category: "product-category.html",
    productDetails: "product-details.html",
    checkout: "checkout.html",
  };
  FRESH_DIRECT.shopUrl = FD_ROUTES.shop;

  function buildLink(message) {
    return (
      "https://wa.me/" +
      FRESH_DIRECT.whatsappNumber +
      "?text=" +
      encodeURIComponent(message)
    );
  }

  function messageFor(el) {
    var mode = el.getAttribute("data-whatsapp") || "general";
    if (mode === "product") {
      var name = el.getAttribute("data-product") || "meat";
      var qty = el.getAttribute("data-qty") || "1";
      var unit = el.getAttribute("data-unit") || "";
      var variant = el.getAttribute("data-variant") || "";
      var what = variant ? name + " — " + variant : name;
      return (
        "Hello O'Toosin Farms! I would like to order: " +
        what +
        " (Qty: " +
        qty +
        (unit && unit !== variant ? " " + unit : "") +
        "). Please confirm availability and delivery."
      );
    }
    if (mode === "cart") {
      return (
        "Hello O'Toosin Farms! I would like to place an order from the website. " +
        "Please help me complete my order."
      );
    }
    if (mode === "restock") {
      var item = el.getAttribute("data-product") || "meat";
      return (
        "Hello O'Toosin Farms! Please let me know when " +
        item +
        " is back in stock. Thank you."
      );
    }
    return FRESH_DIRECT.defaultMessage;
  }

  // Wire every WhatsApp entry point from the single config value.
  function wireWhatsApp() {
    var links = document.querySelectorAll("[data-whatsapp]");
    for (var i = 0; i < links.length; i++) {
      links[i].setAttribute("href", buildLink(messageFor(links[i])));
      links[i].setAttribute("target", "_blank");
      links[i].setAttribute("rel", "noopener");
    }
  }

  // Footer year stays current without template edits.
  function wireYear() {
    var nodes = document.querySelectorAll("[data-fd-year]");
    var year = String(new Date().getFullYear());
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = year;
    }
  }

  // Accessible state for the existing off-canvas mobile menu system.
  function wireMenuA11y() {
    var toggles = document.querySelectorAll(".vs-menu-toggle");
    for (var i = 0; i < toggles.length; i++) {
      if (!toggles[i].hasAttribute("aria-label")) {
        toggles[i].setAttribute("aria-label", "Open menu");
      }
      if (!toggles[i].hasAttribute("aria-expanded")) {
        toggles[i].setAttribute("aria-expanded", "false");
      }
    }
  }

  // Category Show More / Show Less. Extra cards carry .fd-cat-extra and
  // start hidden; the toggle reveals or collapses them in place without
  // touching the grid. Works at every breakpoint (no width-specific logic).
  function wireCategoryToggle() {
    var toggle = document.getElementById("fd-cat-toggle");
    if (!toggle) {
      return;
    }
    var extra = document.querySelectorAll(".fd-cat-extra");
    if (!extra.length) {
      toggle.style.display = "none";
      return;
    }
    toggle.addEventListener("click", function () {
      var expanded = toggle.getAttribute("aria-expanded") === "true";
      for (var i = 0; i < extra.length; i++) {
        if (expanded) {
          extra[i].setAttribute("hidden", "");
          extra[i].classList.remove("fd-reveal");
        } else {
          extra[i].removeAttribute("hidden");
          // Re-trigger the reveal animation on each expansion.
          extra[i].classList.remove("fd-reveal");
          void extra[i].offsetWidth;
          extra[i].classList.add("fd-reveal");
        }
      }
      toggle.setAttribute("aria-expanded", expanded ? "false" : "true");
      toggle.textContent = expanded ? "Show More" : "Show Less";
    });
  }

  /* ==========================================================================
     STAGE 2 — shared cart store + toasts + shop filtering.
     DOM-driven on purpose: product identity comes from card data-*
     attributes (id/name/price/unit/category/image), so the Django backend
     can later replace the markup (or a JSON feed) without touching this
     logic. Cart persists in localStorage under a versioned key.
     Additive only: on pages without shop/cart markup these init as no-ops,
     so Home behavior is preserved (its Add buttons simply start working).
     ========================================================================== */

  function esc(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c];
    });
  }

  function fmtNaira(n) {
    return "\u20A6" + Math.round(Number(n) || 0).toLocaleString("en-NG");
  }

  /* ---------- KG quantity helpers (shared by PDP / cart / checkout) ----------
     A line is a KG line only when its unit/variant text mentions "kg"
     (e.g. variant id "1kg" / label "1kg"). All other units (bunch, pack,
     bottle, basket, piece, tuber, …) keep the legacy integer behavior. */
  var FD_KG_MIN = 0.5;
  var FD_KG_MAX = 99;
  var FD_EACH_MAX = 99;

  function fdIsKgText(s) {
    return typeof s === "string" && /kg/i.test(s);
  }

  function fdIsKgVariant(v) {
    return !!v && (fdIsKgText(v.id) || fdIsKgText(v.label));
  }

  function fdIsKgItem(item) {
    return !!item && (fdIsKgText(item.variant) || fdIsKgText(item.unit));
  }

  function fdRound2(n) {
    return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
  }

  // Display: strip trailing zeros ("1", "1.5", "1.3", "2") — never "1.0".
  function fdFormatQty(q, isKg) {
    var n = fdRound2(q);
    if (!isKg) {
      return String(Math.round(n));
    }
    var s = n.toFixed(2);
    s = s.replace(/\.?0+$/, "");
    return s === "" ? "0" : s;
  }

  function fdQtyLabel(q, isKg) {
    var s = fdFormatQty(q, isKg);
    return isKg ? s + " kg" : s;
  }

  function fdLineTotal(price, qty) {
    return Math.round(Number(price) * Number(qty));
  }

  // Manual kg entry: up to 2 decimals, 0.5–99. Never snaps to 0.5 steps.
  function fdParseKgQty(raw) {
    if (raw === null || raw === undefined) {
      return null;
    }
    var s = String(raw).trim();
    if (!/^\d+(\.\d{1,2})?$/.test(s)) {
      return null;
    }
    var n = fdRound2(parseFloat(s));
    if (!isFinite(n) || n < FD_KG_MIN || n > FD_KG_MAX) {
      return null;
    }
    return n;
  }

  function fdClampQty(q, isKg) {
    var n = fdRound2(q);
    if (!isFinite(n)) {
      return isKg ? 1 : 1;
    }
    if (isKg) {
      if (n < FD_KG_MIN) {
        return FD_KG_MIN;
      }
      if (n > FD_KG_MAX) {
        return FD_KG_MAX;
      }
      return n;
    }
    n = Math.round(n);
    if (n < 1) {
      return 1;
    }
    if (n > FD_EACH_MAX) {
      return FD_EACH_MAX;
    }
    return n;
  }

  /* ---------- Toasts ---------- */
  function showToast(message) {
    var region = document.getElementById("fd-toast-region");
    if (!region) {
      region = document.createElement("div");
      region.id = "fd-toast-region";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    var toast = document.createElement("div");
    toast.className = "fd-toast";
    var icon = document.createElement("i");
    icon.className = "fas fa-check-circle";
    icon.setAttribute("aria-hidden", "true");
    toast.appendChild(icon);
    toast.appendChild(document.createTextNode(message));
    region.appendChild(toast);
    window.setTimeout(function () {
      toast.classList.add("is-leaving");
      window.setTimeout(function () {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 320);
    }, 2600);
  }

  /* ---------- Cart store ---------- */
  var CART_KEY = "freshdirect_cart_v1";

  function cartLoad() {
    try {
      var raw = window.localStorage.getItem(CART_KEY);
      var items = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(items)) {
        return [];
      }
      // Drop the retired Harvest Castle produce seed (mock-*) from older
      // carts so the O'Toosin meat catalogue is the only possible source.
      items = items.filter(function (item) {
        return item && !/^mock-/.test(String(item.id || ""));
      });
      // Migrate pre-variant lines (Stage 2) to keyed lines.
      for (var i = 0; i < items.length; i++) {
        if (!items[i].key) {
          items[i].variant = items[i].variant || items[i].unit || "";
          items[i].key = items[i].id + "__" + items[i].variant;
        }
        // Normalize quantities: KG lines keep decimals, others stay ints.
        var q = Number(items[i].qty);
        if (isFinite(q)) {
          items[i].qty = fdClampQty(q, fdIsKgItem(items[i]));
        } else {
          items[i].qty = 1;
        }
        items[i].price = Number(items[i].price) || 0;
      }
      return items;
    } catch (e) {
      return [];
    }
  }

  function cartSave(items) {
    try {
      window.localStorage.setItem(CART_KEY, JSON.stringify(items));
    } catch (e) {
      /* storage unavailable (private mode) — cart still works in memory */
    }
    try {
      document.dispatchEvent(new CustomEvent("freshdirect:cart"));
    } catch (e) {
      /* CustomEvent unavailable — other surfaces still re-render normally */
    }
  }

  function cartCount(items) {
    var n = 0;
    for (var i = 0; i < items.length; i++) {
      n = fdRound2(n + Number(items[i].qty));
    }
    return n;
  }

  function cartSubtotal(items) {
    var n = 0;
    for (var i = 0; i < items.length; i++) {
      n += fdLineTotal(items[i].price, items[i].qty);
    }
    return n;
  }

  // Navbar badge = number of cart line items (never a KG quantity like
  // "1.5" or "3.3"). cartCount() above is kept for any other consumer.
  function refreshBadges() {
    var n = String(cartLoad().length);
    var badges = document.querySelectorAll(
      "#fd-cart-count, #fd-cart-count-mobile"
    );
    for (var i = 0; i < badges.length; i++) {
      badges[i].textContent = n;
    }
  }

  function productFromCard(card) {
    var img = card.querySelector(".product-img img");
    var id = card.getAttribute("data-product-id");
    // Card-level lines carry the variant PK, matching the PDP, while the
    // visible label is kept separately for the cart.
    var variantId = card.getAttribute("data-variant-id") || card.getAttribute("data-unit") || "";
    var variant = card.getAttribute("data-variant-label") || card.getAttribute("data-unit") || "";
    return {
      key: id + "__" + variantId,
      id: id,
      variantId: variantId,
      name: card.getAttribute("data-product-name") || "Fresh produce",
      variant: variant,
      price: parseInt(card.getAttribute("data-price"), 10) || 0,
      unit: variant,
      category: card.getAttribute("data-category") || "",
      image: img ? img.getAttribute("src") : "",
      alt: img ? img.getAttribute("alt") || "" : "",
    };
  }

  function renderCartPanel() {
    var panels = document.querySelectorAll(
      ".sideCart-wrapper .widget_shopping_cart_content"
    );
    if (!panels.length) {
      return;
    }
    var items = cartLoad();
    for (var p = 0; p < panels.length; p++) {
      renderOneCartPanel(panels[p], items);
    }
    // New WhatsApp links injected above need wiring.
    wireWhatsApp();
  }

  function renderOneCartPanel(panel, items) {
    var empty = panel.querySelector(".fd-cart-empty");
    var oldList = panel.querySelector("[data-cart-items]");
    if (oldList && oldList.parentNode) {
      oldList.parentNode.removeChild(oldList);
    }
    var oldFoot = panel.querySelector("[data-cart-foot]");
    if (oldFoot && oldFoot.parentNode) {
      oldFoot.parentNode.removeChild(oldFoot);
    }
    if (!items.length) {
      if (empty) {
        empty.removeAttribute("hidden");
      }
      return;
    }
    if (empty) {
      empty.setAttribute("hidden", "");
    }
    var list = document.createElement("ul");
    list.className = "fd-cart-items";
    list.setAttribute("data-cart-items", "");
    list.setAttribute("aria-label", "Cart items");
    for (var i = 0; i < items.length; i++) {
      list.appendChild(cartItemNode(items[i]));
    }
    var buttons = panel.querySelector(".buttons");
    panel.insertBefore(list, buttons || null);

    var foot = document.createElement("div");
    foot.setAttribute("data-cart-foot", "");
    var total = document.createElement("div");
    total.className = "fd-cart-total";
    var label = document.createElement("span");
    label.textContent = "Subtotal";
    var value = document.createElement("strong");
    value.setAttribute("data-cart-subtotal", "");
    value.textContent = fmtNaira(cartSubtotal(items));
    total.appendChild(label);
    total.appendChild(value);
    foot.appendChild(total);
    panel.insertBefore(foot, buttons || null);
  }

  function cartItemNode(item) {
    var li = document.createElement("li");
    li.className = "fd-cart-item";
    li.setAttribute("data-id", item.id);
    li.setAttribute("data-key", item.key);

    var img = document.createElement("img");
    img.setAttribute("src", item.image);
    img.setAttribute("alt", item.alt || item.name);
    img.setAttribute("loading", "lazy");
    img.setAttribute("decoding", "async");
    li.appendChild(img);

    var info = document.createElement("div");
    info.className = "fd-cart-info";
    var name = document.createElement("strong");
    name.textContent = item.name;
    var meta = document.createElement("span");
    var variantLabel = item.variant || item.unit || "";
    var itemKg = fdIsKgItem(item);
    // KG lines show the live total ("1.4 kg · ₦2,800"), never the static
    // variant pack label ("2kg") which can't reflect edited quantities.
    if (itemKg) {
      meta.textContent = fdQtyLabel(item.qty, true) + " · " + fmtNaira(item.price);
      meta.setAttribute("data-cart-meta", "kg");
    } else {
      meta.textContent =
        (variantLabel ? variantLabel + " · " : "") + fmtNaira(item.price);
    }
    var qty = document.createElement("div");
    qty.className = "fd-qty";
    var dec = document.createElement("button");
    dec.type = "button";
    dec.setAttribute("data-cart-dec", item.key);
    dec.setAttribute("aria-label", "Decrease quantity of " + item.name + (itemKg ? " by 0.5 kilograms" : ""));
    dec.innerHTML = '<i class="fas fa-minus" aria-hidden="true"></i>';
    var inc = document.createElement("button");
    inc.type = "button";
    inc.setAttribute("data-cart-inc", item.key);
    inc.setAttribute("aria-label", "Increase quantity of " + item.name + (itemKg ? " by 0.5 kilograms" : ""));
    inc.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i>';
    qty.appendChild(dec);
    var valueNodes = cartQtyValueNodes(item, itemKg);
    for (var vn = 0; vn < valueNodes.length; vn++) {
      qty.appendChild(valueNodes[vn]);
    }
    qty.appendChild(inc);
    info.appendChild(name);
    info.appendChild(meta);
    info.appendChild(qty);
    li.appendChild(info);

    var line = document.createElement("div");
    line.className = "fd-cart-line";
    var amount = document.createElement("strong");
    amount.textContent = fmtNaira(fdLineTotal(item.price, item.qty));
    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "fd-cart-remove";
    remove.setAttribute("data-cart-remove", item.key);
    remove.setAttribute("aria-label", "Remove " + item.name + " from cart");
    remove.innerHTML = '<i class="far fa-trash-alt" aria-hidden="true"></i>';
    line.appendChild(amount);
    line.appendChild(remove);
    li.appendChild(line);
    return li;
  }

  /* ---------- Server-authoritative cart checks ---------- */
  function cartCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

  function cartVariantRef(item) {
    if (item && item.variantId) {
      return String(item.variantId);
    }
    var key = String((item && item.key) || "");
    var split = key.lastIndexOf("__");
    return split >= 0 ? key.slice(split + 2) : "";
  }

  function cartRequestLines(items) {
    var lines = [];
    for (var i = 0; i < items.length; i++) {
      lines.push({
        product: items[i].id,
        variant: cartVariantRef(items[i]),
        quantity: items[i].qty,
        price: items[i].price,
      });
    }
    return lines;
  }

  function cartValidateServer(items, strict) {
    var url = strict ? FD_ROUTES.checkoutValidate : FD_ROUTES.cartValidate;
    if (!url || !window.fetch) {
      return Promise.resolve(null);
    }
    return window
      .fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": cartCsrfToken(),
        },
        body: JSON.stringify({ items: cartRequestLines(items) }),
      })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!data || typeof data !== "object") {
            return null;
          }
          data._httpStatus = response.status;
          return data;
        });
      })
      .catch(function () {
        return null;
      });
  }

  function cartApplyServer(result) {
    var items = result && Array.isArray(result.items) ? result.items : [];
    cartSave(items);
    refreshBadges();
    renderCartPanel();
    renderCartPage();
  }

  function cartServerMessages(result) {
    if (!result) {
      return [];
    }
    var out = [];
    var seen = {};
    var groups = [result.errors || [], result.notices || []];
    for (var g = 0; g < groups.length; g++) {
      for (var i = 0; i < groups[g].length; i++) {
        var text = groups[g][i] && groups[g][i].message;
        if (text && !seen[text]) {
          seen[text] = true;
          out.push(text);
        }
      }
    }
    return out;
  }

  function cartShowServerMessages(result) {
    var messages = cartServerMessages(result);
    for (var i = 0; i < messages.length && i < 3; i++) {
      showToast(messages[i]);
    }
    if (messages.length > 3) {
      showToast(
        (messages.length - 3) + " more cart update" +
        (messages.length - 3 === 1 ? "" : "s") + " applied."
      );
    }
  }

  function cartCommit(candidate, successMessage) {
    return cartValidateServer(candidate, false).then(function (result) {
      if (!result) {
        showToast("We could not check your cart. Please try again.");
        return false;
      }
      if (result._httpStatus >= 400) {
        cartShowServerMessages(result);
        return false;
      }
      cartApplyServer(result);
      if (successMessage && result.ok) {
        showToast(successMessage);
      }
      cartShowServerMessages(result);
      return result.ok;
    });
  }

  function cartReconcile() {
    var items = cartLoad();
    if (!items.length) {
      return Promise.resolve();
    }
    return cartValidateServer(items, false).then(function (result) {
      if (!result) {
        return;
      }
      if (result._httpStatus < 400) {
        cartApplyServer(result);
      }
      cartShowServerMessages(result);
    });
  }

  // Merge a full line item by variant key. Used by Product Details;
  // card-level adds go through cartAdd below (same merge, qty 1).
  function cartAddLine(line) {
    if (!line || !line.key || !line.id || !(line.price >= 0)) {
      return Promise.resolve(false);
    }
    var lineIsKg = fdIsKgItem(line);
    var lineQty = fdClampQty(Number(line.qty), lineIsKg);
    if (lineIsKg) {
      if (!(lineQty >= FD_KG_MIN)) {
        return Promise.resolve(false);
      }
    } else if (!(lineQty >= 1)) {
      return Promise.resolve(false);
    }
    var items = cartLoad();
    items.push({
      key: line.key,
      id: line.id,
      variantId: cartVariantRef(line),
      name: line.name,
      variant: line.variant || "",
      price: line.price,
      qty: lineQty,
      unit: line.unit || "",
      category: line.category || "",
      image: line.image || "",
      alt: line.alt || "",
    });
    var label = line.name + (line.variant && !lineIsKg ? " — " + line.variant : "");
    return cartCommit(
      items,
      "Added to cart: " + label + (lineIsKg ? " · " : " × ") +
        fdQtyLabel(lineQty, lineIsKg)
    );
  }

  function cartAdd(id, card) {
    if (!id || !card) {
      return;
    }
    var data = productFromCard(card);
    data.qty = 1;
    cartAddLine(data);
  }

  // KG lines step by 0.5 from their current qty (1.3 + 0.5 = 1.8);
  // every other unit keeps the legacy ±1 integer steps.
  function cartBump(key, delta) {
    var items = cartLoad();
    var changed = false;
    for (var i = 0; i < items.length; i++) {
      if (items[i].key === key) {
        var isKg = fdIsKgItem(items[i]);
        var step = isKg ? 0.5 : 1;
        var dir = delta >= 0 ? 1 : -1;
        items[i].qty = fdClampQty(
          fdRound2(Number(items[i].qty) + dir * step),
          isKg
        );
        changed = true;
      }
    }
    if (!changed) {
      return Promise.resolve(false);
    }
    return cartCommit(items);
  }

  /* ---------- Editable KG quantities in cart surfaces ----------
     KG lines render an <input> (+ static "kg" suffix) inside the existing
     .fd-qty pill; non-KG lines keep the legacy <span>. Typing updates the
     line price + subtotals live (no re-render, no focus loss); commit
     happens on change/blur/Enter through the single cart store so the
     preview, cart.html, checkout, and WhatsApp always agree. */
  function cartQtyValueNodes(item, isKg) {
    if (!isKg) {
      var count = document.createElement("span");
      count.setAttribute("aria-live", "polite");
      count.textContent = fdQtyLabel(item.qty, false);
      return [count];
    }
    var input = document.createElement("input");
    input.type = "text";
    input.className = "fd-cart-qty-input";
    input.value = fdFormatQty(item.qty, true);
    input.setAttribute("data-cart-qty", item.key);
    input.setAttribute("inputmode", "decimal");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("spellcheck", "false");
    input.setAttribute(
      "aria-label",
      "Quantity in kilograms for " + item.name
    );
    var suffix = document.createElement("span");
    suffix.className = "fd-qty-unit";
    suffix.setAttribute("aria-hidden", "true");
    suffix.textContent = "kg";
    var row = document.createElement("span");
    row.className = "fd-qty-entry-row";
    row.appendChild(input);
    row.appendChild(suffix);
    var hint = document.createElement("span");
    hint.className = "fd-kg-hint";
    hint.textContent = "Type exact kg";
    var entry = document.createElement("span");
    entry.className = "fd-qty-entry has-kg-input";
    entry.appendChild(row);
    entry.appendChild(hint);
    return [entry];
  }

  // Commit path: single store write, then re-render every surface.
  function cartSetQty(key, qty) {
    var items = cartLoad();
    var changed = false;
    for (var i = 0; i < items.length; i++) {
      if (items[i].key === key) {
        items[i].qty = fdClampQty(Number(qty), fdIsKgItem(items[i]));
        changed = true;
      }
    }
    if (!changed) {
      return Promise.resolve(false);
    }
    return cartCommit(items);
  }

  // Live path while typing: patch the visible line price + every subtotal
  // from the existing KG pricing (fdLineTotal) without re-rendering, so
  // focus and the half-typed value are never disturbed.
  function cartLivePrice(input, qty) {
    var key = input.getAttribute("data-cart-qty");
    var items = cartLoad();
    var price = null;
    for (var i = 0; i < items.length; i++) {
      if (items[i].key === key) {
        price = items[i].price;
      }
    }
    if (price === null) {
      return;
    }
    var li = null;
    if (input.closest) {
      li = input.closest('li[data-key]');
    }
    if (li) {
      var amount = li.querySelector(".fd-cart-line strong, .fd-cartpage-line");
      if (amount) {
        var lineTotal = fmtNaira(fdLineTotal(price, qty));
        amount.textContent = lineTotal;
        if (amount.classList.contains("fd-cartpage-line")) {
          amount.setAttribute("aria-label", "Line total: " + lineTotal);
        }
      }
      // Keep the "1.4 kg · ₦2,800" line in step with the typed quantity.
      var liveMeta = li.querySelector("[data-cart-meta]");
      if (liveMeta) {
        var kind = liveMeta.getAttribute("data-cart-meta");
        if (kind === "kg") {
          liveMeta.textContent =
            fdQtyLabel(qty, true) + " · " + fmtNaira(price);
        }
      }
    }
    var sub = 0;
    for (var j = 0; j < items.length; j++) {
      sub += fdLineTotal(
        items[j].price,
        items[j].key === key ? qty : items[j].qty
      );
    }
    var nodes = document.querySelectorAll(
      "[data-cart-subtotal], [data-cart-total], " +
        "[data-checkout-subtotal], [data-checkout-total]"
    );
    for (var s = 0; s < nodes.length; s++) {
      nodes[s].textContent = fmtNaira(sub);
    }
  }

  function cartQtyInputFromEvent(ev) {
    if (!ev || !ev.target || !ev.target.closest) {
      return null;
    }
    return ev.target.closest("[data-cart-qty]");
  }

  var fdCartQtyWired = false;
  function wireCartQtyInputs() {
    if (fdCartQtyWired) {
      return;
    }
    fdCartQtyWired = true;
    // Live: valid keystrokes refresh prices at once, invalid ones wait.
    document.addEventListener("input", function (ev) {
      var t = cartQtyInputFromEvent(ev);
      if (!t) {
        return;
      }
      var parsed = fdParseKgQty(t.value);
      if (parsed === null) {
        return;
      }
      t.removeAttribute("aria-invalid");
      cartLivePrice(t, parsed);
    });
    // Commit on blur / select / Enter (re-renders from the single store;
    // invalid values revert to the stored quantity).
    document.addEventListener("change", function (ev) {
      var t = cartQtyInputFromEvent(ev);
      if (!t) {
        return;
      }
      var parsed = fdParseKgQty(t.value);
      if (parsed === null) {
        showToast("Enter a weight between 0.5 kg and 99 kg.");
        renderCartPanel();
        renderCartPage();
        return;
      }
      t.removeAttribute("aria-invalid");
      cartSetQty(t.getAttribute("data-cart-qty"), parsed);
    });
    document.addEventListener("keydown", function (ev) {
      if (!ev || ev.key !== "Enter") {
        return;
      }
      var t = cartQtyInputFromEvent(ev);
      if (!t) {
        return;
      }
      ev.preventDefault();
      t.blur();
    });
  }

  function cartRemove(key) {
    var items = cartLoad();
    var kept = [];
    var removed = "";
    for (var i = 0; i < items.length; i++) {
      if (items[i].key === key) {
        removed = items[i].name;
      } else {
        kept.push(items[i]);
      }
    }
    if (!kept.length) {
      cartSave([]);
      refreshBadges();
      renderCartPanel();
      renderCartPage();
      if (removed) {
        showToast("Removed from cart: " + removed);
      }
      return Promise.resolve(true);
    }
    return cartCommit(
      kept,
      removed ? "Removed from cart: " + removed : ""
    );
  }

  function cartClear() {
    var items = cartLoad();
    if (!items.length) {
      return;
    }
    cartSave([]);
    refreshBadges();
    renderCartPanel();
    renderCartPage();
    showToast("Cart cleared.");
  }

  /* ==========================================================================
     STAGE 4 — full Cart page renderer (cart.html only).
     Consumes the SAME cart store (localStorage freshdirect_cart_v1) and
     the SAME FD_CATALOG — no Cart-specific dataset. Quantity/remove reuse
     the delegated [data-cart-inc/dec/remove] handlers in wireCart(), so
     Grid/List, side cart, and this page can never disagree: every mutation
     re-renders all three surfaces from the one store.
     ========================================================================== */

  // Corrupted lines (unknown product, malformed data) must never crash the
  // page: they render as removable "unavailable" rows and are excluded
  // from the product subtotal. Prices are never invented.
  function cartPageValid(item) {
    if (
      !item ||
      typeof item.id !== "string" ||
      !item.id ||
      typeof item.name !== "string" ||
      !item.name ||
      !isFinite(item.price) ||
      item.price < 0 ||
      !isFinite(item.qty)
    ) {
      return false;
    }
    if (fdIsKgItem(item)) {
      return item.qty >= FD_KG_MIN && item.qty <= FD_KG_MAX;
    }
    return item.qty >= 1 && Math.round(item.qty) === Number(item.qty);
  }

  // Stored image first; fall back to the catalog so older lines and
  // hand-built lines still show the right photo. Never invents prices.
  function cartPageMedia(item) {
    if (item.image) {
      return { src: item.image, alt: item.alt || item.name };
    }
    var entry = FD_CATALOG[item.id];
    if (entry && entry.images && entry.images[0]) {
      return { src: entry.images[0].src, alt: entry.images[0].alt || item.name };
    }
    return { src: "", alt: item.name };
  }

  function cartPageNode(item) {
    var li = document.createElement("li");
    li.className = "fd-cartpage-item";
    li.setAttribute("data-key", item.key);

    var media = cartPageMedia(item);
    var entry = FD_CATALOG[item.id];
    var detailUrl = entry && entry.url
      ? entry.url
      : FD_ROUTES.productDetails + "?id=" + encodeURIComponent(item.id);

    if (!cartPageValid(item)) {
      li.classList.add("is-invalid");
      li.innerHTML =
        '<div class="fd-cartpage-info">' +
        "<strong>" + esc(item.name || "Unknown item") + "</strong>" +
        '<span class="fd-cartpage-note">This item is no longer available.</span>' +
        "</div>" +
        '<button type="button" class="fd-cart-remove" data-cart-remove="' + esc(item.key) +
        '" aria-label="Remove ' + esc(item.name || "unknown item") + ' from cart">' +
        '<i class="far fa-trash-alt" aria-hidden="true"></i><span>Remove</span></button>';
      return li;
    }

    var variantLabel = item.variant || item.unit || "";
    var a = document.createElement("a");
    a.className = "fd-cartpage-img";
    a.setAttribute("href", detailUrl);
    a.setAttribute("aria-label", "View " + item.name);
    var img = document.createElement("img");
    if (media.src) {
      img.setAttribute("src", media.src);
    }
    img.setAttribute("alt", media.alt);
    img.setAttribute("loading", "lazy");
    img.setAttribute("decoding", "async");
    a.appendChild(img);
    li.appendChild(a);

    var info = document.createElement("div");
    info.className = "fd-cartpage-info";
    var top = document.createElement("div");
    top.className = "fd-cartpage-top";
    var idWrap = document.createElement("div");
    idWrap.className = "fd-cartpage-id";
    var name = document.createElement("strong");
    var link = document.createElement("a");
    link.setAttribute("href", detailUrl);
    link.textContent = item.name;
    name.appendChild(link);
    var meta = document.createElement("span");
    var pageKg = fdIsKgItem(item);
    var catalogEntry = FD_CATALOG[item.id];
    if (pageKg) {
      var metaParts = [];
      if (catalogEntry && catalogEntry.condition) {
        metaParts.push(catalogEntry.condition);
      }
      var meatType = item.category || (catalogEntry && catalogEntry.category) || "";
      if (meatType) {
        metaParts.push(meatType);
      }
      metaParts.push(fmtNaira(item.price) + "/kg");
      meta.textContent = metaParts.join(" · ");
      meta.setAttribute("data-cart-meta", "kg-price");
    } else {
      meta.textContent =
        (variantLabel ? variantLabel + " · " : "") + fmtNaira(item.price) + " each";
    }
    idWrap.appendChild(name);
    idWrap.appendChild(meta);
    var lineWrap = document.createElement("div");
    lineWrap.className = "fd-cartpage-line-wrap";
    var lineLabel = document.createElement("span");
    lineLabel.className = "fd-cartpage-line-label";
    lineLabel.textContent = "Line total";
    var line = document.createElement("strong");
    line.className = "fd-cartpage-line";
    line.textContent = fmtNaira(fdLineTotal(item.price, item.qty));
    line.setAttribute(
      "aria-label",
      "Line total: " + fmtNaira(fdLineTotal(item.price, item.qty))
    );
    lineWrap.appendChild(lineLabel);
    lineWrap.appendChild(line);
    top.appendChild(idWrap);
    top.appendChild(lineWrap);
    info.appendChild(top);

    var actions = document.createElement("div");
    actions.className = "fd-cartpage-actions";
    var weight = document.createElement("div");
    weight.className = "fd-cartpage-weight";
    var weightLabel = document.createElement("span");
    weightLabel.className = "fd-cartpage-weight-label";
    weightLabel.textContent = "Weight";
    weight.appendChild(weightLabel);
    var qty = document.createElement("div");
    qty.className = "fd-qty";
    qty.setAttribute("role", "group");
    qty.setAttribute("aria-label", "Quantity for " + item.name + (pageKg ? " in kilograms" : ""));
    var dec = document.createElement("button");
    dec.type = "button";
    dec.setAttribute("data-cart-dec", item.key);
    dec.setAttribute("aria-label", "Decrease quantity of " + item.name + (pageKg ? " by 0.5 kilograms" : ""));
    dec.innerHTML = '<i class="fas fa-minus" aria-hidden="true"></i>';
    var inc = document.createElement("button");
    inc.type = "button";
    inc.setAttribute("data-cart-inc", item.key);
    inc.setAttribute("aria-label", "Increase quantity of " + item.name + (pageKg ? " by 0.5 kilograms" : ""));
    inc.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i>';
    qty.appendChild(dec);
    var pageValueNodes = cartQtyValueNodes(item, pageKg);
    for (var pvn = 0; pvn < pageValueNodes.length; pvn++) {
      qty.appendChild(pageValueNodes[pvn]);
    }
    qty.appendChild(inc);
    weight.appendChild(qty);
    actions.appendChild(weight);

    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "fd-cart-remove";
    remove.setAttribute("data-cart-remove", item.key);
    remove.setAttribute("aria-label", "Remove " + item.name + " from cart");
    remove.innerHTML =
      '<i class="far fa-trash-alt" aria-hidden="true"></i><span>Remove</span>';
    actions.appendChild(remove);
    info.appendChild(actions);
    li.appendChild(info);
    return li;
  }

  function renderCartPage() {
    var wrap = document.getElementById("fd-cart-wrap");
    if (!wrap) {
      return;
    }
    var list = document.getElementById("fd-cart-list");
    var main = document.getElementById("fd-cart-main");
    var empty = document.getElementById("fd-cart-empty");
    var items = cartLoad();
    if (!list || !main || !empty) {
      return;
    }
    list.innerHTML = "";
    if (!items.length) {
      main.setAttribute("hidden", "");
      empty.removeAttribute("hidden");
      setCartLineCount(wrap, 0);
      setCartMoney(wrap, 0);
      return;
    }
    empty.setAttribute("hidden", "");
    main.removeAttribute("hidden");
    var valid = [];
    for (var i = 0; i < items.length; i++) {
      list.appendChild(cartPageNode(items[i]));
      if (cartPageValid(items[i])) {
        valid.push(items[i]);
      }
    }
    setCartLineCount(wrap, items.length);
    setCartMoney(wrap, cartSubtotal(valid));
  }

  function setCartLineCount(wrap, count) {
    var nodes = wrap.querySelectorAll("[data-cart-line-count]");
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = count + (count === 1 ? " item" : " items");
    }
  }

  function setCartMoney(wrap, amount) {
    var value = fmtNaira(amount);
    var subs = wrap.querySelectorAll("[data-cart-subtotal]");
    for (var s = 0; s < subs.length; s++) {
      subs[s].textContent = value;
    }
    var totals = wrap.querySelectorAll("[data-cart-total]");
    for (var t = 0; t < totals.length; t++) {
      totals[t].textContent = value;
    }
  }

  function wireCartPage() {
    if (!document.getElementById("fd-cart-wrap")) {
      return;
    }
    renderCartPage();
  }

  // Single delegated listener covers Home + Shop (current and future cards).
  function wireCart() {
    refreshBadges();
    renderCartPanel();
    wireCartQtyInputs();
    cartReconcile();
    document.addEventListener("click", function (ev) {
      var add = ev.target.closest("[data-add-to-cart]");
      if (add && !add.disabled) {
        ev.preventDefault();
        cartAdd(
          add.getAttribute("data-add-to-cart"),
          add.closest("article.product-style1")
        );
        return;
      }
      var inc = ev.target.closest("[data-cart-inc]");
      if (inc) {
        ev.preventDefault();
        cartBump(inc.getAttribute("data-cart-inc"), 1);
        return;
      }
      var dec = ev.target.closest("[data-cart-dec]");
      if (dec) {
        ev.preventDefault();
        cartBump(dec.getAttribute("data-cart-dec"), -1);
        return;
      }
      var rem = ev.target.closest("[data-cart-remove]");
      if (rem) {
        ev.preventDefault();
        cartRemove(rem.getAttribute("data-cart-remove"));
        return;
      }
      var clear = ev.target.closest("[data-cart-clear]");
      if (clear) {
        ev.preventDefault();
        cartClear();
      }
    });
  }

  // Header badge now reflects the real cart (was a static "0" placeholder).
  function wireCartBadge() {
    refreshBadges();
  }

  /* ---------- Shop filtering / search / sort (Shop page only) ---------- */
  function wireShop() {
    var toolbar = document.getElementById("fd-shop-toolbar");
    var grid = document.getElementById("fd-shop-grid");
    if (!toolbar || !grid) {
      return;
    }
    var cards = Array.prototype.slice.call(
      grid.querySelectorAll("article.product-style1")
    );
    var search = document.getElementById("fd-shop-search");
    var pills = document.getElementById("fd-shop-pills");
    var avail = document.getElementById("fd-shop-avail");
    var sort = document.getElementById("fd-shop-sort");
    var count = document.getElementById("fd-shop-count");
    var empty = document.getElementById("fd-shop-empty");
    var reset = document.getElementById("fd-shop-reset");

    var state = { q: "", cat: "all", avail: "all", sort: "featured" };

    function matches(card) {
      var name = (card.getAttribute("data-product-name") || "").toLowerCase();
      var cat = (card.getAttribute("data-category") || "").toLowerCase();
      var stock = card.getAttribute("data-stock") || "in";
      if (state.q && name.indexOf(state.q) === -1 && cat.indexOf(state.q) === -1) {
        return false;
      }
      if (state.cat !== "all" && cat !== state.cat) {
        return false;
      }
      if (state.avail === "in" && stock === "out") {
        return false;
      }
      if (state.avail === "out" && stock !== "out") {
        return false;
      }
      return true;
    }

    function priceOf(card) {
      return parseInt(card.getAttribute("data-price"), 10) || 0;
    }

    function nameOf(card) {
      return (card.getAttribute("data-product-name") || "").toLowerCase();
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
      }
      for (var i = 0; i < cards.length; i++) {
        cards[i].parentNode.style.display = "none";
      }
      for (var j = 0; j < visible.length; j++) {
        visible[j].parentNode.style.display = "";
        grid.appendChild(visible[j].parentNode);
      }
      if (count) {
        count.textContent =
          "Showing " + visible.length + " of " + cards.length + " products";
      }
      if (empty) {
        if (visible.length) {
          empty.setAttribute("hidden", "");
        } else {
          empty.removeAttribute("hidden");
        }
      }
    }

    // Category pills link to the category page (backend-ready: Django
    // filters product-category.html by ?category=<name> server-side).
    // Clicking a pill navigates instead of client-side filtering, so the
    // grid on this page only responds to search / availability / sort.
    // The ?category=… deep link below still highlights the matching pill
    // through aria-pressed so the current category reads clearly.
    function buildPills() {
      if (!pills) {
        return;
      }
      var seen = [];
      for (var i = 0; i < cards.length; i++) {
        var cat = cards[i].getAttribute("data-category") || "";
        if (cat && seen.indexOf(cat) === -1) {
          seen.push(cat);
        }
      }
      seen.sort();
      pills.innerHTML = "";
      var all = document.createElement("a");
      all.className = "fd-cat-pill";
      all.textContent = "All";
      all.setAttribute("href", FD_ROUTES.shop);
      all.setAttribute("data-cat", "all");
      all.setAttribute("aria-pressed", "true");
      pills.appendChild(all);
      for (var j = 0; j < seen.length; j++) {
        (function (cat) {
          var b = document.createElement("a");
          b.className = "fd-cat-pill";
          b.textContent = cat;
          b.setAttribute(
            "href",
            FD_ROUTES.category + "?category=" + encodeURIComponent(cat)
          );
          b.setAttribute("data-cat", cat.toLowerCase());
          b.setAttribute("aria-pressed", "false");
          pills.appendChild(b);
        })(seen[j]);
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
    if (avail) {
      avail.addEventListener("change", function () {
        state.avail = avail.value;
        apply();
      });
    }
    if (sort) {
      sort.addEventListener("change", function () {
        state.sort = sort.value;
        apply();
      });
    }
    if (reset) {
      reset.addEventListener("click", function () {
        state.q = "";
        state.cat = "all";
        state.avail = "all";
        state.sort = "featured";
        if (search) {
          search.value = "";
        }
        if (avail) {
          avail.value = "all";
        }
        if (sort) {
          sort.value = "featured";
        }
        var allBtns = pills ? pills.querySelectorAll("[data-cat]") : [];
        for (var i = 0; i < allBtns.length; i++) {
          allBtns[i].setAttribute(
            "aria-pressed",
            allBtns[i].getAttribute("data-cat") === "all" ? "true" : "false"
          );
        }
        apply();
        if (search) {
          search.focus();
        }
      });
    }

    // Deep link (?category=…): home category tiles land here pre-filtered,
    // with the matching pill highlighted through the same aria-pressed
    // state a manual pill click sets. Backend-ready: a Django
    // /products/?category=<slug> URL resolves the same way, since matching
    // is case-insensitive against the live pill set. Unknown or missing
    // values keep "All" so a stale link can never strand the shopper on
    // an empty page.
    function applyUrlCategory() {
      if (!pills) {
        return;
      }
      var slug = null;
      try {
        slug = new URLSearchParams(window.location.search).get("category");
      } catch (e) {
        slug = null;
      }
      if (slug === null) {
        return;
      }
      slug = String(slug).trim().toLowerCase();
      if (!slug) {
        return;
      }
      var btns = pills.querySelectorAll("[data-cat]");
      for (var i = 0; i < btns.length; i++) {
        if ((btns[i].getAttribute("data-cat") || "").toLowerCase() === slug) {
          state.cat = btns[i].getAttribute("data-cat");
          for (var k = 0; k < btns.length; k++) {
            btns[k].setAttribute(
              "aria-pressed",
              btns[k] === btns[i] ? "true" : "false"
            );
          }
          return;
        }
      }
    }

    buildPills();
    applyUrlCategory();
    apply();

    // Async-ready states for the future Django feed. Static markup renders
    // instantly today, so these stay dormant until real fetching lands.
    window.FreshDirectShop = {
      loading: function (on) {
        grid.setAttribute("aria-busy", on ? "true" : "false");
      },
      state: state,
      apply: apply,
    };
  }

  /* ==========================================================================
     STAGE 3 — product catalogue from the Django-rendered JSON feed.
     --------------------------------------------------------------------------
     FD_CATALOG is populated by the storefront context processor and injected
     before this script. Every product, variant, image and price comes from
     the database; this file never carries product data of its own.
     status: "in" | "limited" | "out" (never invent counts).
     ========================================================================== */
  var FD_CATALOG = window.FD_CATALOG || {};

  window.FreshDirectCatalog = FD_CATALOG;

  function pdpReadId() {
    var root = document.getElementById("fd-pdp");
    if (root && root.getAttribute("data-product-id")) {
      return root.getAttribute("data-product-id");
    }
    try {
      var params = new URLSearchParams(window.location.search);
      return params.get("id") || "";
    } catch (e) {
      return "";
    }
  }

  /* ---------- Product Details renderer (product-details.html only) ---------- */
  function wirePDP() {
    var root = document.getElementById("fd-pdp");
    if (!root) {
      return;
    }
    var main = document.getElementById("fd-pdp-main");
    var missing = document.getElementById("fd-pdp-missing");
    var errorBox = document.getElementById("fd-pdp-error");
    try {
      var product = FD_CATALOG[pdpReadId()];
      if (!product) {
        if (main) {
          main.setAttribute("hidden", "");
        }
        if (missing) {
          missing.removeAttribute("hidden");
        }
        document.title = "Product not found | O’TOOSIN Farms";
        return;
      }
      renderPDP(root, product);
      if (main) {
        main.setAttribute("aria-busy", "false");
      }
    } catch (e) {
      if (main) {
        main.setAttribute("hidden", "");
      }
      if (errorBox) {
        errorBox.removeAttribute("hidden");
      }
    }
  }

  function pdpStatusMeta(status) {
    if (status === "out") {
      return { badge: "Out of Stock", stockLabel: "Out of stock", cls: "is-out", stockCls: "is-out", schema: "https://schema.org/OutOfStock" };
    }
    if (status === "limited") {
      return { badge: "Limited", stockLabel: "Limited availability", cls: "is-low", stockCls: "is-low", schema: "https://schema.org/LimitedAvailability" };
    }
    return { badge: "Available", stockLabel: "In stock", cls: "", stockCls: "is-in", schema: "https://schema.org/InStock" };
  }

  function pdpCategorySlug(category) {
    return String(category || "").replace(/\s+/g, "-");
  }

  function pdpIsProduceCategory(category) {
    return category === "Eggs" || category === "Veggies" || category === "Fruits";
  }

  function pdpTypeLabel(category) {
    if (category === "Live Animals") {
      return "Animal type:";
    }
    if (pdpIsProduceCategory(category)) {
      return "Produce type:";
    }
    if (category === "Fish") {
      return "Fish type:";
    }
    if (category === "Pork" || category === "Chicken" || category === "Turkey" ||
        category === "Beef" || category === "Goat Meat") {
      return "Meat type:";
    }
    return "Product type:";
  }

  function pdpDetailLabel(category) {
    if (category === "Live Animals") {
      return "Animal:";
    }
    if (pdpIsProduceCategory(category)) {
      return "Pack:";
    }
    return "Cut:";
  }

  function renderPDP(root, product) {
    var meta = pdpStatusMeta(product.status);
    var def = null;
    for (var d = 0; d < product.variants.length; d++) {
      if (product.variants[d].id === product.defaultVariant) {
        def = product.variants[d];
      }
    }
    var state = {
      product: product,
      variant: def || product.variants[0],
      qty: 1,
    };

    // Identity.
    setText("fd-pdp-cat", product.group ? product.category + " \u00b7 " + product.group : product.category);
    setText("fd-pdp-name", product.name);
    setText("fd-pdp-desc", product.desc);
    setText("fd-pdp-crumb", product.name);
    setText("fd-pdp-condition", product.condition || product.badge || meta.badge);
    setText("fd-pdp-cut", product.cut || "");
    var cutPill = document.getElementById("fd-pdp-cut");
    if (cutPill) {
      cutPill.hidden = !product.cut;
    }
    var crumb = document.getElementById("fd-pdp-crumb");
    if (crumb) {
      crumb.setAttribute("aria-current", "page");
    }
    var crumbCat = document.getElementById("fd-pdp-crumb-cat");
    if (crumbCat) {
      crumbCat.textContent = product.category;
      crumbCat.setAttribute(
        "href",
        product.categoryUrl ||
          FD_ROUTES.category + "?category=" + encodeURIComponent(product.categorySlug || pdpCategorySlug(product.category))
      );
    }

    // Availability badge.
    var badge = document.getElementById("fd-pdp-badge");
    if (badge) {
      badge.textContent = product.badge || meta.badge;
      badge.className = "fd-badge" + (meta.cls ? " " + meta.cls : "");
    }
    var stock = document.getElementById("fd-pdp-stock");
    if (stock) {
      stock.textContent = meta.stockLabel;
      stock.className = "fd-pdp-stock " + meta.stockCls;
    }

    // Gallery (structure supports many images; mock has one).
    renderPDPGallery(product);

    // Variants.
    var wrap = document.getElementById("fd-pdp-variants");
    if (wrap) {
      wrap.innerHTML = "";
      for (var i = 0; i < product.variants.length; i++) {
        (function (v, isDefault) {
          var b = document.createElement("button");
          b.type = "button";
          b.className = "fd-variant-btn";
          b.textContent = v.label;
          b.setAttribute("data-variant-id", v.id);
          b.setAttribute("aria-pressed", isDefault ? "true" : "false");
          b.addEventListener("click", function () {
            state.variant = v;
            // Keep the chosen amount but fit the new variant's rules:
            // KG keeps decimals (≥0.5), each-unit snaps to an integer (≥1).
            if (fdIsKgVariant(v)) {
              state.qty = fdClampQty(Number(state.qty) || 1, true);
            } else {
              state.qty = fdClampQty(Math.round(Number(state.qty) || 1), false);
            }
            var btns = wrap.querySelectorAll("[data-variant-id]");
            for (var k = 0; k < btns.length; k++) {
              btns[k].setAttribute(
                "aria-pressed",
                btns[k] === b ? "true" : "false"
              );
            }
            pdpSync(root, state);
          });
          wrap.appendChild(b);
        })(product.variants[i], product.variants[i] === state.variant);
      }
      var single = product.variants.length < 2;
      wrap.classList.toggle("is-single", single);
      var legend = document.getElementById("fd-pdp-variant-label");
      if (legend && single) {
        legend.textContent = "Selling unit";
      }
    }

    // Quantity stepper. KG variants step by 0.5 from the current value
    // (1.3 + 0.5 = 1.8, never snapped); other units keep legacy ±1 ints.
    // KG variants get a typable decimal input; other units keep the span.
    var decBtn = document.getElementById("fd-pdp-dec");
    var incBtn = document.getElementById("fd-pdp-inc");
    if (decBtn) {
      decBtn.addEventListener("click", function () {
        var isKg = fdIsKgVariant(state.variant);
        var step = isKg ? 0.5 : 1;
        var next = fdRound2(Number(state.qty) - step);
        next = fdClampQty(next, isKg);
        if (fdRound2(next) !== fdRound2(Number(state.qty))) {
          state.qty = next;
          pdpSync(root, state);
        } else {
          pdpSync(root, state);
        }
      });
    }
    if (incBtn) {
      incBtn.addEventListener("click", function () {
        var isKg = fdIsKgVariant(state.variant);
        var step = isKg ? 0.5 : 1;
        var next = fdRound2(Number(state.qty) + step);
        next = fdClampQty(next, isKg);
        if (fdRound2(next) !== fdRound2(Number(state.qty))) {
          state.qty = next;
          pdpSync(root, state);
        } else {
          pdpSync(root, state);
        }
      });
    }
    pdpEnsureQtyControl(state);
    var qtyInit = document.getElementById("fd-pdp-qty");
    if (qtyInit && qtyInit.tagName !== "INPUT") {
      qtyInit.textContent = "1";
    }

    // Purchase actions use the website cart/checkout only.
    var addBtn = document.getElementById("fd-pdp-add");
    var buyBtn = document.getElementById("fd-pdp-buy");
    var out = product.status === "out";
    var addSelection = function () {
      return cartAddLine({
        key: product.id + "__" + state.variant.id,
        id: product.id,
        variantId: state.variant.id,
        name: product.name,
        variant: state.variant.label,
        price: state.variant.price,
        qty: state.qty,
        unit: state.variant.label,
        category: product.category,
        image: product.images[0].src,
        alt: product.images[0].alt,
      });
    };
    if (addBtn) {
      if (out) {
        addBtn.disabled = true;
        addBtn.setAttribute("aria-disabled", "true");
        addBtn.textContent = "Out of Stock";
      } else {
        addBtn.addEventListener("click", function () {
          addSelection().then(function (added) {
            if (added) {
              // Reset for the next selection so a later variant/quantity
              // choice is always deliberate (never a stale qty surprise).
              state.qty = 1;
              pdpSync(root, state);
            } else {
              showToast("Something went wrong. Please try again.");
            }
          });
        });
      }
    }
    if (buyBtn) {
      if (out) {
        buyBtn.disabled = true;
        buyBtn.setAttribute("aria-disabled", "true");
        buyBtn.textContent = "Out of Stock";
      } else {
        buyBtn.addEventListener("click", function () {
          addSelection().then(function (added) {
            if (added) {
              window.location.href = FD_ROUTES.checkout;
            } else {
              showToast("Something went wrong. Please try again.");
            }
          });
        });
      }
    }

    // Supporting facts.
    setText("fd-pdp-fact-cat", product.group || product.category);
    setText("fd-pdp-fact-type", product.name);
    setText("fd-pdp-fact-type-label", pdpTypeLabel(product.category));
    setText("fd-pdp-fact-condition", product.condition || product.badge || meta.badge);
    setText("fd-pdp-fact-cut", product.cut || "");
    setText("fd-pdp-fact-cut-label", pdpDetailLabel(product.category));
    var cutFact = document.getElementById("fd-pdp-fact-cut");
    var cutFactLabel = document.getElementById("fd-pdp-fact-cut-label");
    var cutFactItem = cutFact && cutFact.closest ? cutFact.closest("li") : null;
    if (cutFactItem) {
      cutFactItem.hidden = !product.cut;
    }
    if (cutFact) {
      cutFact.hidden = !product.cut;
    }
    if (cutFactLabel) {
      cutFactLabel.hidden = !product.cut;
    }
    setText("fd-pdp-fact-price", product.priceBasis || "Per kilogram");
    setText(
      "fd-pdp-fact-options",
      product.variants.map(function (v) {
        return v.label;
      }).join(", ")
    );

    renderPDPRelated(product);
    pdpSync(root, state);
    pdpSEO(product, meta);
  }

  // KG qty control: an <input> (decimal keyboard, no native step
  // validation) for KG variants, the original <span> otherwise. Same pill
  // styling, same position — no layout change.
  function pdpEnsureQtyControl(state) {
    var isKg = fdIsKgVariant(state.variant);
    var el = document.getElementById("fd-pdp-qty");
    if (!el) {
      return null;
    }
    var entry = el.closest ? el.closest(".fd-qty-entry") : null;
    if (entry) {
      entry.classList.toggle("has-kg-input", isKg);
      entry.classList.toggle("is-each", !isKg);
    }
    var suffix = document.getElementById("fd-pdp-qty-unit");
    if (suffix) {
      suffix.textContent = isKg ? "kg" : "";
      suffix.hidden = !isKg;
    }
    var wantInput = isKg;
    var hasInput = el.tagName === "INPUT";
    if (wantInput && !hasInput) {
      var input = document.createElement("input");
      input.id = "fd-pdp-qty";
      input.type = "text";
      input.setAttribute("inputmode", "decimal");
      input.setAttribute("autocomplete", "off");
      input.setAttribute("autocapitalize", "off");
      input.setAttribute("spellcheck", "false");
      input.setAttribute("aria-label", "Quantity in kilograms");
      input.setAttribute("aria-describedby", "fd-pdp-kg-hint");
      input.className = "fd-pdp-qty-input";
      input.value = fdFormatQty(state.qty, true);
      if (el.parentNode) {
        el.parentNode.replaceChild(input, el);
      }
      pdpWireQtyInput(input, state);
      return input;
    }
    if (!wantInput && hasInput) {
      var span = document.createElement("span");
      span.id = "fd-pdp-qty";
      span.setAttribute("aria-live", "polite");
      span.textContent = fdFormatQty(state.qty, false);
      if (el.parentNode) {
        el.parentNode.replaceChild(span, el);
      }
      return span;
    }
    return el;
  }

  function pdpWireQtyInput(input, state) {
    if (!input || input.getAttribute("data-fd-wired") === "true") {
      return;
    }
    input.setAttribute("data-fd-wired", "true");
    // Live: update the price as soon as the value parses — never rewrite
    // what the customer is still typing.
    input.addEventListener("input", function () {
      var parsed = fdParseKgQty(input.value);
      if (parsed === null) {
        input.removeAttribute("aria-invalid");
        return;
      }
      state.qty = parsed;
      pdpSyncPrices(state);
    });
    var commit = function () {
      var parsed = fdParseKgQty(input.value);
      if (parsed === null) {
        if (String(input.value).trim() !== "") {
          input.setAttribute("aria-invalid", "true");
        }
        input.value = fdFormatQty(state.qty, true);
        input.removeAttribute("aria-invalid");
        pdpSyncPrices(state);
        return;
      }
      input.removeAttribute("aria-invalid");
      state.qty = parsed;
      input.value = fdFormatQty(state.qty, true);
      pdpSyncPrices(state);
    };
    input.addEventListener("change", commit);
    input.addEventListener("blur", commit);
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        commit();
      }
    });
  }

  // Price-only refresh used while typing (input keeps focus + raw text).
  function pdpSyncPrices(state) {
    var v = state.variant;
    var isKg = fdIsKgVariant(state.variant);
    var amount = document.getElementById("fd-pdp-total-amount");
    if (amount) {
      amount.textContent = fmtNaira(fdLineTotal(v.price, state.qty));
    }
    var detail = document.getElementById("fd-pdp-total-detail");
    if (detail) {
      detail.textContent =
        "\u00b7 " + fdQtyLabel(state.qty, isKg) + " \u00d7 " + fmtNaira(v.price) +
        (isKg ? "/kg" : " " + (state.product.priceUnit || "each"));
    }
  }

  function pdpSync(root, state) {
    var v = state.variant;
    var isKg = fdIsKgVariant(state.variant);
    setText("fd-pdp-price", fmtNaira(v.price));
    setText("fd-pdp-unit", state.product.priceUnit || v.label);
    setText("fd-pdp-qty-label", isKg ? "Quantity (kg)" : "Quantity");
    var el = pdpEnsureQtyControl(state);
    if (el) {
      if (el.tagName === "INPUT") {
        // Don't clobber mid-typing; sync only when not focused.
        if (document.activeElement !== el) {
          el.value = fdFormatQty(state.qty, true);
        }
        el.setAttribute("aria-label", "Quantity in kilograms");
      } else {
        el.textContent = fdFormatQty(state.qty, isKg);
      }
    }
    var decBtn = document.getElementById("fd-pdp-dec");
    var incBtn = document.getElementById("fd-pdp-inc");
    if (decBtn) {
      decBtn.setAttribute(
        "aria-label",
        isKg ? "Decrease quantity by 0.5 kilograms" : "Decrease quantity"
      );
      var atMin = isKg
        ? Number(state.qty) <= FD_KG_MIN
        : Number(state.qty) <= 1;
      decBtn.disabled = !!atMin;
    }
    if (incBtn) {
      incBtn.setAttribute(
        "aria-label",
        isKg ? "Increase quantity by 0.5 kilograms" : "Increase quantity"
      );
      incBtn.disabled = Number(state.qty) >= FD_KG_MAX;
    }
    pdpSyncPrices(state);
    void root;
  }

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) {
      el.textContent = text;
    }
  }

  function renderPDPGallery(product) {
    var img = document.getElementById("fd-pdp-img");
    var zoom = document.getElementById("fd-pdp-zoom");
    var thumbs = document.getElementById("fd-pdp-thumbs");
    var first = product.images[0];
    if (img) {
      img.setAttribute("src", first.src);
      img.setAttribute("alt", first.alt);
      img.setAttribute("width", String(first.w));
      img.setAttribute("height", String(first.h));
    }
    if (zoom) {
      zoom.setAttribute("href", first.src);
    }
    if (!thumbs) {
      return;
    }
    thumbs.innerHTML = "";
    if (product.images.length < 2) {
      thumbs.setAttribute("hidden", "");
      return;
    }
    thumbs.removeAttribute("hidden");
    for (var i = 0; i < product.images.length; i++) {
      (function (im, firstOne) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "fd-pdp-thumb";
        b.setAttribute("aria-pressed", firstOne ? "true" : "false");
        b.setAttribute("aria-label", "View image: " + im.alt);
        var t = document.createElement("img");
        t.setAttribute("src", im.src);
        t.setAttribute("alt", "");
        t.setAttribute("loading", "lazy");
        t.setAttribute("decoding", "async");
        b.appendChild(t);
        b.addEventListener("click", function () {
          if (img) {
            img.setAttribute("src", im.src);
            img.setAttribute("alt", im.alt);
          }
          if (zoom) {
            zoom.setAttribute("href", im.src);
          }
          var all = thumbs.querySelectorAll(".fd-pdp-thumb");
          for (var k = 0; k < all.length; k++) {
            all[k].setAttribute("aria-pressed", all[k] === b ? "true" : "false");
          }
        });
        thumbs.appendChild(b);
      })(product.images[i], i === 0);
    }
  }

  function renderPDPRelated(product) {
    var grid = document.getElementById("fd-pdp-related");
    if (!grid) {
      return;
    }
    var ids = Object.keys(FD_CATALOG);
    var same = [];
    var rest = [];
    for (var i = 0; i < ids.length; i++) {
      if (ids[i] === product.id) {
        continue;
      }
      if (FD_CATALOG[ids[i]].category === product.category) {
        same.push(ids[i]);
      } else {
        rest.push(ids[i]);
      }
    }
    var pick = same.concat(rest).slice(0, 4);
    // Keep the canonical meat order (Pork first) in every mixed list.
    pick.sort(function (a, b) {
      return ids.indexOf(a) - ids.indexOf(b);
    });
    grid.innerHTML = "";
    for (var j = 0; j < pick.length; j++) {
      var node = pdpCardNode(FD_CATALOG[pick[j]]);
      grid.appendChild(node);
      // List-view descriptions come from the single catalog (same as Shop);
      // inject now so dynamically rendered cards match static ones.
      var dynCard = node.querySelector("article.product-style1");
      if (dynCard) {
        shopDescFor(dynCard);
      }
    }
    // Refresh the header count after the dynamic render. The related grid
    // deliberately shows four recommendations, so report that same pool.
    fdUpdateCount("fd-pdp-related", "fd-pdp-count", pick.length);
  }

  /* ==========================================================================
     STAGE 3D — SHARED PRODUCT-CARD ARCHITECTURE (locked).
     The static markup on Shop (product.html #fd-shop-grid) is the MASTER:
       article.product-style1
         [data-product-id / data-product-name / data-price / data-unit /
          data-category / data-stock]
         > .fd-badge? + .product-img > img + .product-about
           (cat / title / unit / .fd-buy-row[price + Add] /
            .fd-secondary-row[View product])
     data-unit carries the variant ID (e.g. "1kg", "bunch") matching Shop;
     the visible unit line is derived by fdUnitDisplay() to match Shop text
     (e.g. "1kg pack", "Per bunch"). Price is ALWAYS the default variant —
     Shop cards display the default variant, never variants[0].
     Home (#featured) and PDP related (#fd-pdp-related) reuse this exact
     structure. List presentation is CSS-only (#fd-shop-grid.is-list);
     never duplicate markup or datasets for grid vs list.
     ========================================================================== */
  function fdDefaultVariant(p) {
    for (var i = 0; i < p.variants.length; i++) {
      if (p.variants[i].id === p.defaultVariant) {
        return p.variants[i];
      }
    }
    return p.variants[0];
  }

  // Shop-master unit display: variant IDs ("1kg","bunch") render as Shop
  // text ("1kg pack","Per bunch"). Labels already starting with "Per "
  // pass through untouched.
  function fdUnitDisplay(p, v) {
    var variant = v || fdDefaultVariant(p);
    var label = variant.label || "";
    if (/^per\s/i.test(label)) {
      return label;
    }
    if (/^\d+(?:\.\d+)?\s*[a-z]/i.test(label)) {
      return label + (/kg$/i.test(label) ? " pack" : "");
    }
    if (/^(bunch|tuber|piece)$/i.test(label)) {
      return "Per " + label;
    }
    return label;
  }

  // Canonical badge HTML for a card. Mirrors Shop master: an explicit
  // p.badge ("Fresh") for featured in-stock lines, status badges otherwise.
  function fdBadgeHtml(p, meta) {
    if (p.badge && p.status === "in") {
      return '<span class="fd-badge">' + esc(p.badge) + "</span>";
    }
    if (p.status === "in") {
      return "";
    }
    return '<span class="fd-badge ' + meta.cls + '">' + meta.badge + "</span>";
  }

  // Related cards reuse the exact Home/Shop card language via this shared
  // builder (single data source: FD_CATALOG). Exposed below as
  // window.FreshDirectCard for future sections — always build cards through
  // it instead of hand-writing new markup.
  function pdpCardNode(p) {
    var col = document.createElement("div");
    col.className = "col-6 col-md-4 col-lg-3";
    var out = p.status === "out";
    var meta = pdpStatusMeta(p.status);
    var def = fdDefaultVariant(p);

    var article = document.createElement("article");
    article.className = "product-style1" + (out ? " is-out" : "");
    article.setAttribute("data-product-id", p.id);
    article.setAttribute("data-product-name", p.name);
    article.setAttribute("data-price", String(def.price));
    article.setAttribute("data-unit", def.label);
    article.setAttribute("data-variant-id", def.id);
    article.setAttribute("data-variant-label", def.label);
    article.setAttribute("data-category", p.category);
    article.setAttribute("data-stock", p.status);
    var detailUrl = p.url || FD_ROUTES.productDetails + "?id=" + encodeURIComponent(p.id);

    var about =
      '<div class="product-img"><img src="' + esc(p.images[0].src) + '" alt="' +
      esc(p.images[0].alt) + '" width="' + p.images[0].w + '" height="' +
      p.images[0].h + '" loading="lazy" decoding="async"></div>' +
      '<div class="product-about">' +
      '<span class="fd-product-cat">' + esc(p.group ? p.category + " \\u00b7 " + p.group : p.category) + "</span>" +
      '<h3 class="product-title"><a href="' + esc(detailUrl) + '">' +
      esc(p.name) + "</a></h3>" +
      '<p class="fd-product-unit">' + esc(fdUnitDisplay(p, def)) + "</p>" +
      '<div class="fd-buy-row"><span class="price">' + fmtNaira(def.price) + "</span>";
    if (out) {
      about +=
        '<button type="button" class="vs-btn fd-add-btn" disabled aria-disabled="true">Out of Stock</button></div>' +
        '<div class="fd-secondary-row"><a href="' + esc(detailUrl) +
        '" class="fd-view-link">View product</a></div>';
    } else {
      about +=
        '<button type="button" class="vs-btn fd-add-btn" data-add-to-cart="' + esc(p.id) +
        '">Add to Cart</button></div>' +
        '<div class="fd-secondary-row"><a href="' + esc(detailUrl) +
        '" class="fd-view-link">View product</a></div>';
    }
    about += "</div>";

    var tmp = document.createElement("div");
    tmp.innerHTML = fdBadgeHtml(p, meta) + about;
    while (tmp.firstChild) {
      article.appendChild(tmp.firstChild);
    }
    col.appendChild(article);
    return col;
  }

  function unitLabel(p) {
    return fdUnitDisplay(p, fdDefaultVariant(p));
  }

  // Single shared entry point for future sections (never hand-roll cards).
  window.FreshDirectCard = {
    defaultVariant: fdDefaultVariant,
    unitDisplay: fdUnitDisplay,
    buildRelated: pdpCardNode,
  };

  function pdpSEO(product, meta) {
    document.title = product.name + " | O’TOOSIN Farms";
    var base = product.variants[0];
    for (var i = 0; i < product.variants.length; i++) {
      if (product.variants[i].id === product.defaultVariant) {
        base = product.variants[i];
      }
    }
    var condition = product.condition || product.badge || "";
    var priceBasis = product.priceBasis || "Priced per unit";
    var descriptor = product.category === "Live Animals"
      ? "Live animal"
      : (condition ? condition + " " + product.category : product.category);
    var description =
      product.name + " (" + descriptor + ") from O’TOOSIN Farms. " +
      priceBasis + ". Choose your quantity and check out on the website.";
    var desc = document.querySelector('meta[name="description"]');
    if (desc) {
      desc.setAttribute("content", description);
    }
    var keywords = document.querySelector('meta[name="keywords"]');
    if (keywords) {
      keywords.setAttribute(
        "content",
        product.name + ", " + product.category + ", " + condition +
          ", O’TOOSIN Farms, farm shop, buy online"
      );
    }
    var og = document.querySelector('meta[property="og:title"]');
    if (og) {
      og.setAttribute("content", product.name + " | O’TOOSIN Farms");
    }
    var ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) {
      ogDesc.setAttribute("content", description);
    }
    var ogImage = document.querySelector('meta[property="og:image"]');
    if (ogImage) {
      ogImage.setAttribute("content", product.images[0].src);
    }
    var unitText = String(product.priceUnit || "unit").replace(/^per\s+/i, "");
    var ld = document.getElementById("fd-pdp-jsonld");
    if (ld) {
      ld.textContent = JSON.stringify({
        "@context": "https://schema.org",
        "@type": "Product",
        name: product.name,
        category: product.category,
        description: product.desc,
        image: product.images[0].src,
        brand: { "@type": "Brand", name: "O’TOOSIN Farms" },
        offers: {
          "@type": "Offer",
          priceCurrency: "NGN",
          price: base.price,
          availability: meta.schema,
          priceSpecification: {
            "@type": "UnitPriceSpecification",
            price: base.price,
            priceCurrency: "NGN",
            unitText: unitText,
          },
        },
      });
    }
  }

  // Card detail links: static cards point at bare product-details.html, so
  // patch them to the id-based route from each card's own product id.
  // Cards that already carry an id (or future Django URLs) are untouched.
  function wireCardLinks() {
    var cards = document.querySelectorAll("article.product-style1[data-product-id]");
    for (var i = 0; i < cards.length; i++) {
      var id = cards[i].getAttribute("data-product-id");
      if (!id) {
        continue;
      }
      var links = cards[i].querySelectorAll(".product-title a, .fd-view-link");
      for (var j = 0; j < links.length; j++) {
        if (links[j].getAttribute("href") === FD_ROUTES.productDetails) {
          links[j].setAttribute("href", FD_ROUTES.productDetails + "?id=" + encodeURIComponent(id));
        }
      }
    }
  }

  /* ---------- Universal grid/list view (one shared mechanism) ----------
     Same nodes, same data, same cart/WhatsApp/links — only the layout
     class changes, so filters, sorting, and cart state are preserved.
     Descriptions come from the single FD_CATALOG (no second dataset).
     Every product collection (Shop, Home, PDP related, future listings)
     initializes through wireCollectionView() with its own independent
     view state. Never create per-page toggle implementations. */
  var SHOP_VIEW_KEY = "freshdirect_shop_view";
  var HOME_VIEW_KEY = "freshdirect_home_view";
  var RELATED_VIEW_KEY = "freshdirect_related_view";

  function shopDescFor(card) {
    if (card.querySelector(".fd-product-desc")) {
      return;
    }
    var id = card.getAttribute("data-product-id");
    var entry = id && FD_CATALOG[id];
    if (!entry || !entry.desc) {
      return;
    }
    var unit = card.querySelector(".fd-product-unit");
    if (!unit || !unit.parentNode) {
      return;
    }
    var p = document.createElement("p");
    p.className = "fd-product-desc";
    p.textContent = entry.desc;
    unit.parentNode.insertBefore(p, unit.nextSibling);
  }

  function setShopView(grid, buttons, view, persist, storageKey) {
    var list = view === "list";
    if (list) {
      grid.classList.add("is-list");
    } else {
      grid.classList.remove("is-list");
    }
    for (var i = 0; i < buttons.length; i++) {
      var active = buttons[i].getAttribute("data-shop-view") === view;
      buttons[i].setAttribute("aria-pressed", active ? "true" : "false");
    }
    if (persist) {
      try {
        window.sessionStorage.setItem(storageKey || SHOP_VIEW_KEY, view);
      } catch (e) {
        /* private mode — view simply resets next visit */
      }
    }
  }

  // Live "Showing X of Y products" line for section headers. Same
  // language as the Shop result count; read from the actual cards so it
  // can never drift from what is rendered.
  function fdUpdateCount(gridId, countId, total) {
    var grid = document.getElementById(gridId);
    var out = document.getElementById(countId);
    if (!grid || !out) {
      return;
    }
    var n = grid.querySelectorAll("article.product-style1").length;
    var t = typeof total === "number" ? total : n;
    out.textContent = "Showing " + n + " of " + t + " products";
  }

  // Single reusable initializer for any product collection. Same toggle
  // behavior everywhere; each collection keeps its own independent state.
  // countId is optional — Shop omits it (its filter-driven count owns that
  // line and must not be touched).
  function wireCollectionView(gridId, toolbarId, storageKey, countId) {
    var grid = document.getElementById(gridId);
    var toolbar = document.getElementById(toolbarId);
    if (!grid || !toolbar) {
      return;
    }
    var buttons = toolbar.querySelectorAll("[data-shop-view]");
    if (!buttons.length) {
      return;
    }
    var cards = grid.querySelectorAll("article.product-style1");
    for (var i = 0; i < cards.length; i++) {
      shopDescFor(cards[i]);
    }
    var saved = null;
    try {
      saved = window.sessionStorage.getItem(storageKey);
    } catch (e) {
      saved = null;
    }
    setShopView(grid, buttons, saved === "list" ? "list" : "grid", false, storageKey);
    fdUpdateCount(gridId, countId);
    toolbar.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-shop-view]");
      if (!btn) {
        return;
      }
      setShopView(grid, buttons, btn.getAttribute("data-shop-view"), true, storageKey);
    });
  }

  function wireShopView() {
    wireCollectionView("fd-shop-grid", "fd-shop-toolbar", SHOP_VIEW_KEY);
    wireCollectionView("fd-home-grid", "fd-home-toolbar", HOME_VIEW_KEY, "fd-home-count");
    wireCollectionView("fd-pdp-related", "fd-pdp-toolbar", RELATED_VIEW_KEY, "fd-pdp-count");
  }

  /* ==========================================================================
     STAGE 5 — Checkout (checkout.html only). Guest-first, single seller.
     Reads the SAME cart store at submit time (never a copy, never stale);
     lines keep their productId__variantId identity and stored prices.
     Website payment goes through window.FreshDirectPay.initializePayment()
     so Paystack/Flutterwave can plug in later — until a backend verifies
     payment, NO success state is ever shown (see the stub contract below).
     ========================================================================== */

  // Payment abstraction (BACKEND CONTRACT — READ BEFORE INTEGRATING):
  //   FreshDirectPay.initializePayment(order) must be replaced by the real
  //   gateway call. It must resolve only after the PROVIDER + DJANGO backend
  //   confirm payment, and the backend must re-validate product/variant
  //   existence, availability, and prices (frontend totals are display-only).
  //   Until then this stub reports "not-configured" and the UI stops
  //   honestly instead of fabricating a payment-success state.
  window.FreshDirectPay = window.FreshDirectPay || {
    configured: false,
    initializePayment: function (order) {
      void order;
      return { status: "not-configured" };
    },
  };

  function checkoutMode() {
    var checked = document.querySelector('input[name="delivery-mode"]:checked');
    return checked ? checked.value : "on-campus";
  }

  function checkoutMethod() {
    var checked = document.querySelector('input[name="order-method"]:checked');
    return checked ? checked.value : "website";
  }

  function checkoutSetMode(mode, form) {
    var campus = document.getElementById("fd-campus-fields");
    var off = document.getElementById("fd-offcampus-fields");
    if (!campus || !off) {
      return;
    }
    var onCampus = mode !== "off-campus";
    if (onCampus) {
      campus.removeAttribute("hidden");
      off.setAttribute("hidden", "");
      checkoutClearGroup(off, form);
    } else {
      off.removeAttribute("hidden");
      campus.setAttribute("hidden", "");
      checkoutClearGroup(campus, form);
    }
  }

  // Hidden fields must never block submission: clear their values' errors
  // (values are kept so switching back loses nothing).
  function checkoutClearGroup(group, form) {
    var inputs = group.querySelectorAll("input, textarea, select");
    for (var i = 0; i < inputs.length; i++) {
      checkoutSetError(form, inputs[i], "");
    }
  }

  function checkoutSetError(form, input, message) {
    if (!input) {
      return;
    }
    var err = document.getElementById(input.id + "-error");
    if (message) {
      input.setAttribute("aria-invalid", "true");
      if (err) {
        err.textContent = message;
        err.removeAttribute("hidden");
        input.setAttribute("aria-describedby", err.id);
      }
      if (form) {
        form.setAttribute("data-tried", "true");
      }
    } else {
      input.removeAttribute("aria-invalid");
      input.removeAttribute("aria-describedby");
      if (err) {
        err.textContent = "";
        err.setAttribute("hidden", "");
      }
    }
  }

  function checkoutStatus(message, isError) {
    var box = document.getElementById("fd-checkout-status");
    if (!box) {
      return;
    }
    if (!message) {
      box.textContent = "";
      box.setAttribute("hidden", "");
      box.classList.remove("is-error");
      return;
    }
    box.textContent = message;
    box.removeAttribute("hidden");
    box.classList.toggle("is-error", !!isError);
  }

  function checkoutPhoneOk(value) {
    var digits = String(value).replace(/[\s\-()]/g, "");
    return /^(\+?234|0)[789][01]\d{8}$/.test(digits);
  }

  // Builds the backend-friendly order from the LIVE cart + form. Returns
  // null when the cart is empty (empty orders can never be submitted).
  function buildOrder(method) {
    var items = cartLoad();
    var valid = [];
    for (var i = 0; i < items.length; i++) {
      if (cartPageValid(items[i])) {
        valid.push(items[i]);
      }
    }
    if (!valid.length) {
      return null;
    }
    var form = document.getElementById("fd-checkout-form");
    var mode = checkoutMode();
    var get = function (id) {
      var el = document.getElementById(id);
      return el ? el.value.trim() : "";
    };
    var lines = [];
    for (var j = 0; j < valid.length; j++) {
      var it = valid[j];
        lines.push({
        productId: it.id,
        variantId: cartVariantRef(it),
        name: it.name,
        variantLabel: it.variant || it.unit || "",
        quantity: it.qty,
        quantityLabel: fdQtyLabel(it.qty, fdIsKgItem(it)),
        unitPrice: it.price,
        lineTotal: fdLineTotal(it.price, it.qty),
      });
    }
    return {
      customer: {
        name: form ? get("fd-co-name") : "",
        phone: form ? get("fd-co-phone") : "",
        email: form ? get("fd-co-email") : "",
      },
      delivery: {
        mode: mode,
        hostel: mode === "off-campus" ? "" : get("fd-co-hostel"),
        facultyOffice: mode === "off-campus" ? "" : get("fd-co-faculty"),
        roomBlock: mode === "off-campus" ? "" : get("fd-co-room"),
        address: mode === "off-campus" ? get("fd-co-address") : "",
        landmark: mode === "off-campus" ? get("fd-co-landmark") : "",
        instructions: form ? get("fd-co-notes") : "",
      },
      items: lines,
      subtotal: cartSubtotal(valid),
      orderingMethod: method || "website",
    };
  }

  function checkoutValidate() {
    var form = document.getElementById("fd-checkout-form");
    if (!form) {
      return { ok: false, order: null };
    }
    form.setAttribute("data-tried", "true");
    var firstBad = null;
    var need = function (input, ok, message) {
      checkoutSetError(form, input, ok ? "" : message);
      if (!ok && !firstBad) {
        firstBad = input;
      }
      return ok;
    };
    var byId = function (id) {
      return document.getElementById(id);
    };
    var val = function (id) {
      var el = byId(id);
      return el ? el.value.trim() : "";
    };
    var ok = true;
    ok = need(byId("fd-co-name"), val("fd-co-name").length >= 2, "Please enter your full name.") && ok;
    ok = need(byId("fd-co-phone"), checkoutPhoneOk(val("fd-co-phone")), "Please enter a valid Nigerian phone number.") && ok;
    var email = val("fd-co-email");
    ok = need(byId("fd-co-email"), !email || /^\S+@\S+\.\S+$/.test(email), "Please enter a valid email address.") && ok;
    if (checkoutMode() === "off-campus") {
      ok = need(byId("fd-co-address"), val("fd-co-address").length >= 5, "Please enter your full address.") && ok;
    } else {
      ok = need(byId("fd-co-hostel"), val("fd-co-hostel").length >= 2, "Please enter your hostel or building.") && ok;
      ok = need(byId("fd-co-room"), val("fd-co-room").length >= 1, "Please enter your room or block.") && ok;
    }
    if (!ok && firstBad) {
      try {
        firstBad.focus();
      } catch (e) {
        /* focus is best-effort */
      }
    }
    return { ok: ok, order: ok ? buildOrder(checkoutMethod()) : null };
  }

  function checkoutSummary() {
    var wrap = document.getElementById("fd-checkout-wrap");
    if (!wrap) {
      return false;
    }
    var list = document.getElementById("fd-checkout-lines");
    var main = document.getElementById("fd-checkout-main");
    var empty = document.getElementById("fd-checkout-empty");
    if (!list || !main || !empty) {
      return false;
    }
    var items = cartLoad();
    var valid = [];
    for (var i = 0; i < items.length; i++) {
      if (cartPageValid(items[i])) {
        valid.push(items[i]);
      }
    }
    if (!valid.length) {
      main.setAttribute("hidden", "");
      empty.removeAttribute("hidden");
      return false;
    }
    empty.setAttribute("hidden", "");
    main.removeAttribute("hidden");
    list.innerHTML = "";
    for (var j = 0; j < valid.length; j++) {
      (function (it) {
        var li = document.createElement("li");
        var variantLabel = it.variant || it.unit || "";
        var left = document.createElement("div");
        var title = document.createElement("strong");
        title.textContent = it.name + " × " + fdQtyLabel(it.qty, fdIsKgItem(it));
        var sub = document.createElement("span");
        sub.textContent =
          (variantLabel ? variantLabel + " · " : "") + fmtNaira(it.price) + " each";
        left.appendChild(title);
        left.appendChild(sub);
        var amount = document.createElement("strong");
        amount.textContent = fmtNaira(fdLineTotal(it.price, it.qty));
        li.appendChild(left);
        li.appendChild(amount);
        list.appendChild(li);
      })(valid[j]);
    }
    var subtotal = cartSubtotal(valid);
    var subs = wrap.querySelectorAll("[data-checkout-subtotal]");
    for (var s = 0; s < subs.length; s++) {
      subs[s].textContent = fmtNaira(subtotal);
    }
    var totals = wrap.querySelectorAll("[data-checkout-total]");
    for (var t = 0; t < totals.length; t++) {
      totals[t].textContent = fmtNaira(subtotal);
    }
    return true;
  }

  function checkoutWhatsAppMessage(order) {
    var lines = ["Hello Harvest Castle! I would like to place this order:"];
    lines.push("");
    lines.push("Name: " + order.customer.name);
    lines.push("Phone: " + order.customer.phone);
    if (order.customer.email) {
      lines.push("Email: " + order.customer.email);
    }
    lines.push(
      "Delivery: " +
        (order.delivery.mode === "off-campus" ? "Off Campus" : "On Campus")
    );
    if (order.delivery.mode === "off-campus") {
      lines.push("Address: " + order.delivery.address);
      if (order.delivery.landmark) {
        lines.push("Landmark: " + order.delivery.landmark);
      }
    } else {
      lines.push("Hostel/Building: " + order.delivery.hostel);
      lines.push("Room/Block: " + order.delivery.roomBlock);
      if (order.delivery.facultyOffice) {
        lines.push("Faculty/Office: " + order.delivery.facultyOffice);
      }
    }
    if (order.delivery.instructions) {
      lines.push("Instructions: " + order.delivery.instructions);
    }
    for (var i = 0; i < order.items.length; i++) {
      var it = order.items[i];
      var itQty = it.quantityLabel || String(it.quantity);
      // quantityLabel already carries " kg" for KG lines (e.g. "1.3 kg").
      if (!it.quantityLabel && fdIsKgText(it.variantLabel)) {
        itQty = fdQtyLabel(it.quantity, true);
      }
      lines.push("");
      lines.push(
        i + 1 + ". " + it.name +
          (it.variantLabel ? " — " + it.variantLabel : "") +
          " × " + itQty
      );
      lines.push(
        fmtNaira(it.unitPrice) + " each — " + fmtNaira(it.lineTotal)
      );
    }
    lines.push("");
    lines.push("Subtotal: " + fmtNaira(order.subtotal));
    lines.push("Please confirm availability and delivery details.");
    return lines.join("\n");
  }

  function checkoutWhatsAppHref(order) {
    return (
      "https://wa.me/" + FRESH_DIRECT.whatsappNumber + "?text=" +
      encodeURIComponent(checkoutWhatsAppMessage(order))
    );
  }

  function wireCheckout() {
    var wrap = document.getElementById("fd-checkout-wrap");
    if (!wrap) {
      return;
    }
    // checkout.html runs the dedicated otoosin-checkout.js controller. The
    // older fresh-direct checkout wiring must not attach a second submit
    // handler or overwrite its summary on the same page.
    if (document.getElementById("oto-loc-trigger") || document.getElementById("oto-co-name")) {
      return;
    }
    var form = document.getElementById("fd-checkout-form");
    if (!form) {
      return;
    }
    checkoutSummary();

    // Delivery-mode switching: only the visible group's fields validate.
    var modes = form.querySelectorAll('input[name="delivery-mode"]');
    for (var m = 0; m < modes.length; m++) {
      modes[m].addEventListener("change", function () {
        checkoutSetMode(checkoutMode(), form);
        checkoutStatus("");
      });
    }

    // Gentle validation: blur validates only after a first submit attempt;
    // typing always clears that field's error immediately.
    var fields = form.querySelectorAll("input, textarea");
    for (var f = 0; f < fields.length; f++) {
      (function (input) {
        input.addEventListener("blur", function () {
          if (form.getAttribute("data-tried") === "true" && !input.disabled) {
            checkoutValidateField(form, input);
          }
        });
        input.addEventListener("input", function () {
          checkoutSetError(form, input, "");
        });
      })(fields[f]);
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      // Stale-cart protection: re-read the live cart before anything else.
      if (!checkoutSummary()) {
        checkoutStatus("Your cart is empty. Add some fresh produce first.", true);
        return;
      }
      var result = checkoutValidate();
      if (!result.ok || !result.order) {
        checkoutStatus("Please fix the highlighted fields.", true);
        return;
      }
      if (checkoutMethod() === "whatsapp") {
        // Snapshot first (independent of the cart, which is preserved),
        // then hand off to WhatsApp and land on the confirmation state.
        var waOrder = stampOrder(result.order, "submitted");
        saveLastOrder(waOrder);
        window.open(checkoutWhatsAppHref(waOrder), "_blank", "noopener");
        checkoutGo(confirmationUrl(waOrder));
        return;
      }
      // Website path: honest stop until the backend/gateway lands.
      var payment = window.FreshDirectPay.initializePayment(result.order);
      if (payment && payment.status === "not-configured") {
        checkoutStatus(
          "Online payment is not connected yet. Please use “Order via WhatsApp” to complete your purchase — your details above are kept.",
          true
        );
        return;
      }
      checkoutStatus(
        "This order state is not recognized. Please use “Order via WhatsApp”.",
        true
      );
    });

    var waBtn = document.getElementById("fd-checkout-wa");
    if (waBtn) {
      waBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        if (!checkoutSummary()) {
          checkoutStatus("Your cart is empty. Add some fresh produce first.", true);
          return;
        }
        var result = checkoutValidate();
        if (!result.ok || !result.order) {
          checkoutStatus("Please fix the highlighted fields.", true);
          return;
        }
        var waOrder = stampOrder(result.order, "submitted");
        saveLastOrder(waOrder);
        window.open(checkoutWhatsAppHref(waOrder), "_blank", "noopener");
        checkoutGo(confirmationUrl(waOrder));
      });
    }

    // Cart changed elsewhere (back-nav, another tab): never show stale totals.
    window.addEventListener("pageshow", function () {
      checkoutSummary();
    });
    window.addEventListener("storage", function (ev) {
      if (ev && ev.key === "freshdirect_cart_v1") {
        checkoutSummary();
      }
    });
  }

  // Single-field re-check used by gentle blur validation.
  function checkoutValidateField(form, input) {
    var id = input.id;
    var val = input.value.trim();
    if (id === "fd-co-name") {
      checkoutSetError(form, input, val.length >= 2 ? "" : "Please enter your full name.");
    } else if (id === "fd-co-phone") {
      checkoutSetError(form, input, checkoutPhoneOk(val) ? "" : "Please enter a valid Nigerian phone number.");
    } else if (id === "fd-co-email") {
      checkoutSetError(form, input, !val || /^\S+@\S+\.\S+$/.test(val) ? "" : "Please enter a valid email address.");
    } else if (id === "fd-co-hostel") {
      checkoutSetError(form, input, val.length >= 2 ? "" : "Please enter your hostel or building.");
    } else if (id === "fd-co-room") {
      checkoutSetError(form, input, val.length >= 1 ? "" : "Please enter your room or block.");
    } else if (id === "fd-co-address") {
      checkoutSetError(form, input, val.length >= 5 ? "" : "Please enter your full address.");
    }
  }

  /* ==========================================================================
     STAGE 6 — Order confirmation (order-confirmation.html + checkout
     handoff). One saved snapshot (sessionStorage freshdirect_last_order)
     is the ONLY thing the confirmation page reads: the URL carries just
     the order id, never payment state. Statuses: submitted |
     pending | failed | paid. "paid" renders ONLY when the snapshot itself
     carries payment.verified === true plus a reference (a backend-set
     flag) — URL parameters can never confer it. The FD-XXXXXX reference
     below is a CLIENT-SIDE placeholder the Django backend will replace
     with the real order id; it is never presented as a payment reference.
     Cart is preserved on WhatsApp handoff (the snapshot is independent of
     the cart, and the customer may cancel the WhatsApp send).
     ========================================================================== */
  var LAST_ORDER_KEY = "freshdirect_last_order";

  function makeOrderRef() {
    var chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    var out = "";
    try {
      for (var i = 0; i < 6; i++) {
        out += chars.charAt(Math.floor(Math.random() * chars.length));
      }
    } catch (e) {
      out = "000000";
    }
    return "FD-" + out;
  }

  // Stamp a validated buildOrder() result into a storable snapshot.
  function stampOrder(order, status) {
    order.id = makeOrderRef();
    order.status = status;
    order.placedAt = new Date().toISOString();
    order.payment = order.payment || {
      provider: "",
      reference: "",
      status: "unpaid",
      verified: false,
    };
    return order;
  }

  function saveLastOrder(order) {
    try {
      window.sessionStorage.setItem(LAST_ORDER_KEY, JSON.stringify(order));
      return true;
    } catch (e) {
      return false;
    }
  }

  function readLastOrder() {
    try {
      var raw = window.sessionStorage.getItem(LAST_ORDER_KEY);
      if (!raw) {
        return null;
      }
      var order = JSON.parse(raw);
      if (!order || typeof order.id !== "string" || !order.id) {
        return null;
      }
      if (!Array.isArray(order.items) || !order.items.length) {
        return null;
      }
      return order;
    } catch (e) {
      return null;
    }
  }

  // Testable navigation helper (jsdom cannot navigate; records the target).
  function checkoutGo(url) {
    window.__fdLastNav = url;
    window.location.href = url;
  }

  function confirmationUrl(order) {
    return "order-confirmation.html?order=" + encodeURIComponent(order.id);
  }

  // Paid renders ONLY on a backend-verified snapshot flag. Nothing else —
  // not the URL, not a query status, not localStorage — can mark paid.
  function confirmationPaidOk(order) {
    return !!(
      order &&
      order.status === "paid" &&
      order.payment &&
      order.payment.verified === true &&
      order.payment.reference
    );
  }

  function confirmFirstName(order) {
    var name =
      order && order.customer && order.customer.name
        ? String(order.customer.name).trim()
        : "";
    return name ? name.split(/\s+/)[0] : "there";
  }

  function confirmSummaryList(order) {
    var ul = document.createElement("ul");
    ul.className = "fd-checkout-lines";
    for (var i = 0; i < order.items.length; i++) {
      (function (it) {
        var li = document.createElement("li");
        var left = document.createElement("div");
        var title = document.createElement("strong");
        var cQty = it.quantityLabel || String(it.quantity);
        if (!it.quantityLabel && fdIsKgText(it.variantLabel)) {
          cQty = fdQtyLabel(it.quantity, true);
        }
        title.textContent = it.name + " × " + cQty;
        var sub = document.createElement("span");
        sub.textContent =
          (it.variantLabel ? it.variantLabel + " · " : "") +
          fmtNaira(it.unitPrice) +
          " each";
        left.appendChild(title);
        left.appendChild(sub);
        var amount = document.createElement("strong");
        amount.textContent = fmtNaira(it.lineTotal);
        li.appendChild(left);
        li.appendChild(amount);
        ul.appendChild(li);
      })(order.items[i]);
    }
    return ul;
  }

  function confirmDeliveryList(order) {
    var ul = document.createElement("ul");
    ul.className = "fd-pdp-facts";
    var d = order.delivery || {};
    var rows = [];
    rows.push([
      "Mode",
      d.mode === "off-campus" ? "Off Campus" : "On Campus",
    ]);
    if (d.mode === "off-campus") {
      if (d.address) {
        rows.push(["Address", d.address]);
      }
      if (d.landmark) {
        rows.push(["Landmark", d.landmark]);
      }
    } else {
      if (d.hostel) {
        rows.push(["Hostel/Building", d.hostel]);
      }
      if (d.roomBlock) {
        rows.push(["Room/Block", d.roomBlock]);
      }
      if (d.facultyOffice) {
        rows.push(["Faculty/Office", d.facultyOffice]);
      }
    }
    if (d.instructions) {
      rows.push(["Instructions", d.instructions]);
    }
    if (order.customer && order.customer.phone) {
      rows.push(["Contact", order.customer.phone]);
    }
    for (var i = 0; i < rows.length; i++) {
      (function (label, value) {
        var li = document.createElement("li");
        var lab = document.createElement("span");
        lab.textContent = label + ":";
        var val = document.createElement("strong");
        val.textContent = " " + value;
        li.appendChild(lab);
        li.appendChild(val);
        ul.appendChild(li);
      })(rows[i][0], rows[i][1]);
    }
    return ul;
  }

  function confirmAction(href, cls, icon, label) {
    var a = document.createElement("a");
    a.setAttribute("href", href);
    a.className = cls;
    var i = document.createElement("i");
    i.className = icon;
    i.setAttribute("aria-hidden", "true");
    a.appendChild(i);
    a.appendChild(document.createTextNode(label));
    return a;
  }

  function confirmCard(o) {
    var article = document.createElement("article");
    article.className = "fd-confirm-card";

    var head = document.createElement("div");
    head.className = "fd-confirm-head";
    var iconWrap = document.createElement("span");
    iconWrap.className = "fd-confirm-icon" + (o.iconTone ? " " + o.iconTone : "");
    var icon = document.createElement("i");
    icon.className = o.icon;
    icon.setAttribute("aria-hidden", "true");
    iconWrap.appendChild(icon);
    var headText = document.createElement("div");
    var badge = document.createElement("span");
    badge.className = "fd-badge" + (o.badgeTone ? " " + o.badgeTone : "");
    badge.textContent = o.badge;
    var title = document.createElement("h2");
    title.textContent = o.title;
    var lead = document.createElement("p");
    lead.className = "fd-confirm-lead";
    lead.setAttribute("role", "status");
    lead.textContent = o.lead;
    headText.appendChild(badge);
    headText.appendChild(title);
    headText.appendChild(lead);
    head.appendChild(iconWrap);
    head.appendChild(headText);
    article.appendChild(head);

    if (o.ref) {
      var ref = document.createElement("p");
      ref.className = "fd-confirm-ref";
      ref.appendChild(document.createTextNode("Order reference: "));
      var strong = document.createElement("strong");
      strong.textContent = o.ref;
      ref.appendChild(strong);
      article.appendChild(ref);
    }
    if (o.extraRef) {
      var pref = document.createElement("p");
      pref.className = "fd-confirm-ref";
      pref.appendChild(document.createTextNode(o.extraRef[0] + ": "));
      var pstrong = document.createElement("strong");
      pstrong.textContent = o.extraRef[1];
      pref.appendChild(pstrong);
      article.appendChild(pref);
    }

    if (o.order) {
      var sumTitle = document.createElement("h3");
      sumTitle.textContent = "Order summary";
      article.appendChild(sumTitle);
      article.appendChild(confirmSummaryList(o.order));
      var totalRow = document.createElement("div");
      totalRow.className = "fd-cart-summary-row is-total";
      var tLabel = document.createElement("span");
      tLabel.textContent = "Subtotal";
      var tVal = document.createElement("strong");
      tVal.textContent = fmtNaira(o.order.subtotal);
      totalRow.appendChild(tLabel);
      totalRow.appendChild(tVal);
      article.appendChild(totalRow);

      var delTitle = document.createElement("h3");
      delTitle.textContent = "Delivery";
      article.appendChild(delTitle);
      article.appendChild(confirmDeliveryList(o.order));
    }

    if (o.note) {
      var note = document.createElement("p");
      note.className = "fd-pdp-note";
      var ni = document.createElement("i");
      ni.className = "far fa-truck";
      ni.setAttribute("aria-hidden", "true");
      note.appendChild(ni);
      note.appendChild(document.createTextNode(o.note));
      article.appendChild(note);
    }

    var actions = document.createElement("div");
    actions.className = "fd-confirm-actions";
    for (var i = 0; i < o.actions.length; i++) {
      actions.appendChild(o.actions[i]);
    }
    article.appendChild(actions);
    return article;
  }

  function confirmInvalidNode() {
    var box = document.createElement("div");
    box.className = "fd-shop-state";
    box.innerHTML =
      '<i class="far fa-search" aria-hidden="true"></i>' +
      "<h2>Order not found</h2>" +
      "<p>We could not find that order. It may have expired or the link is incorrect.</p>";
    var a = document.createElement("a");
    a.setAttribute("href", FD_ROUTES.shop);
    a.className = "vs-btn";
    a.textContent = "Return to Shop";
    box.appendChild(a);
    return box;
  }

  function renderConfirmation() {
    var mount = document.getElementById("fd-confirm-state");
    if (!mount) {
      return;
    }
    mount.innerHTML = "";
    var params = null;
    try {
      params = new URLSearchParams(window.location.search);
    } catch (e) {
      params = null;
    }
    var urlId = params ? params.get("order") : null;
    var order = readLastOrder();
    // The URL id must match the saved snapshot; a bare/foreign id never
    // renders an order, and URL state is never trusted for payment.
    if (!order || (urlId && urlId !== order.id)) {
      mount.appendChild(confirmInvalidNode());
      document.title = "Order not found | Harvest Castle";
      return;
    }
    if (!urlId) {
      mount.appendChild(confirmInvalidNode());
      document.title = "Order not found | Harvest Castle";
      return;
    }

    var waHref = checkoutWhatsAppHref(order);
    if (order.status === "submitted") {
      mount.appendChild(
        confirmCard({
          icon: "fab fa-whatsapp",
          badge: "Order submitted",
          title: "Thank you, " + confirmFirstName(order),
          lead: "Your order details are ready — send the WhatsApp message to O'Toosin Farms to confirm it. Nothing is paid until we confirm with you.",
          ref: order.id,
          order: order,
          note: "Delivery is arranged personally with you — any delivery fee will be confirmed before anything is prepared.",
          actions: [
            (function () {
              var a = confirmAction("#", "fd-whatsapp-btn", "fab fa-whatsapp", "Open WhatsApp again");
              a.setAttribute("href", waHref);
              a.setAttribute("target", "_blank");
              a.setAttribute("rel", "noopener");
              return a;
            })(),
            confirmAction(FD_ROUTES.shop, "vs-btn", "far fa-shopping-basket", "Continue Shopping"),
          ],
        })
      );
      document.title = "Order " + order.id + " | Harvest Castle";
      return;
    }
    if (order.status === "pending") {
      mount.appendChild(
        confirmCard({
          icon: "far fa-clock",
          iconTone: "is-pending",
          badge: "Payment pending",
          badgeTone: "is-low",
          title: "Your payment is being verified",
          lead: "Please wait while we confirm your payment. Do not try to pay again yet.",
          ref: order.id,
          order: order,
          actions: [
            confirmAction(FD_ROUTES.checkout, "vs-btn", "far fa-redo", "Back to Checkout"),
            confirmAction(FD_ROUTES.shop, "fd-ghost-btn", "far fa-shopping-basket", "Continue Shopping"),
          ],
        })
      );
      document.title = "Payment pending | Harvest Castle";
      return;
    }
    if (order.status === "failed") {
      mount.appendChild(
        confirmCard({
          icon: "far fa-exclamation-circle",
          iconTone: "is-bad",
          badge: "Payment failed",
          badgeTone: "is-out",
          title: "Your payment did not go through",
          lead: "No money was taken for this order. Your cart is unchanged — please try again or order via WhatsApp.",
          ref: order.id,
          order: order,
          actions: [
            confirmAction(FD_ROUTES.checkout, "vs-btn", "far fa-redo", "Try Again"),
            (function () {
              var a = confirmAction("#", "fd-whatsapp-btn", "fab fa-whatsapp", "Order via WhatsApp");
              a.setAttribute("href", waHref);
              a.setAttribute("target", "_blank");
              a.setAttribute("rel", "noopener");
              return a;
            })(),
          ],
        })
      );
      document.title = "Payment failed | Harvest Castle";
      return;
    }
    if (confirmationPaidOk(order)) {
      mount.appendChild(
        confirmCard({
          icon: "fas fa-check-circle",
          badge: "Paid",
          title: "Thank you, " + confirmFirstName(order),
          lead: "Your payment is confirmed. We will contact you shortly to arrange delivery.",
          ref: order.id,
          extraRef: ["Payment reference", order.payment.reference],
          order: order,
          note: "Delivery is arranged personally with you — we will confirm the details before anything is prepared.",
          actions: [
            confirmAction(FD_ROUTES.shop, "vs-btn", "far fa-shopping-basket", "Continue Shopping"),
            confirmAction(FD_ROUTES.home, "fd-ghost-btn", "far fa-home", "Back Home"),
          ],
        })
      );
      document.title = "Order " + order.id + " confirmed | Harvest Castle";
      return;
    }
    // Anything else (including status:"paid" WITHOUT backend verification)
    // is treated as not found — never a success screen.
    mount.appendChild(confirmInvalidNode());
    document.title = "Order not found | Harvest Castle";
  }

  function wireConfirmation() {
    if (!document.getElementById("fd-confirm-state")) {
      return;
    }
    renderConfirmation();
  }

  /* ==========================================================================
     STAGE 12 — Contact form (contact.html #fd-contact-form only).
     --------------------------------------------------------------------------
     Architecture: Contact Form UI -> FreshDirectContact.submitContact()
     -> future Django endpoint. There is NO contact endpoint today, so the
     boundary reports "not-configured" and the UI hands the validated
     message to WhatsApp (the established Harvest Castle channel, wired from
     FRESH_DIRECT.whatsappNumber — never hardcoded here). No success is
     ever claimed that did not happen; no personal data is persisted.
     Django integration = set FRESH_DIRECT.contactEndpoint and replace
     submitContact() with a fetch() POST of the same { name, phone,
     email, subject, message } payload. Validation + markup stay as-is.
     ========================================================================== */

  // Future Django contact endpoint (e.g. "/api/contact/"). Empty means no
  // backend is connected yet — the form then uses the WhatsApp handoff.
  FRESH_DIRECT.contactEndpoint = "";

  // Builds the backend-friendly payload from the live form. Trimmed;
  // optional email is "" when not provided.
  function buildContactPayload() {
    var get = function (id) {
      var el = document.getElementById(id);
      return el ? el.value.trim() : "";
    };
    return {
      name: get("fd-contact-name"),
      phone: get("fd-contact-phone"),
      email: get("fd-contact-email"),
      subject: get("fd-contact-subject"),
      message: get("fd-contact-message"),
    };
  }

  // Submission boundary. Today: always "not-configured" (no endpoint).
  // Django replaces this with a real POST and returns { status: "sent" }
  // on success or { status: "failed" } on error — callers already handle
  // all three states, so no UI changes are needed then.
  function submitContact(payload) {
    void payload;
    if (FRESH_DIRECT.contactEndpoint) {
      return { status: "not-configured" };
    }
    return { status: "not-configured" };
  }

  window.FreshDirectContact = {
    buildPayload: buildContactPayload,
    submit: submitContact,
  };

  function contactStatus(message, isError) {
    var box = document.getElementById("fd-contact-status");
    if (!box) {
      return;
    }
    if (!message) {
      box.textContent = "";
      box.setAttribute("hidden", "");
      box.classList.remove("is-error");
      return;
    }
    box.textContent = message;
    box.removeAttribute("hidden");
    box.classList.toggle("is-error", !!isError);
  }

  function contactValidateField(form, input) {
    var id = input.id;
    var val = input.value.trim();
    if (id === "fd-contact-name") {
      checkoutSetError(form, input, val.length >= 2 ? "" : "Please enter your name.");
    } else if (id === "fd-contact-phone") {
      checkoutSetError(form, input, checkoutPhoneOk(val) ? "" : "Please enter a valid Nigerian phone number.");
    } else if (id === "fd-contact-email") {
      checkoutSetError(form, input, !val || /^\S+@\S+\.\S+$/.test(val) ? "" : "Please enter a valid email address.");
    } else if (id === "fd-contact-subject") {
      checkoutSetError(form, input, val.length >= 2 ? "" : "Please enter a subject.");
    } else if (id === "fd-contact-message") {
      checkoutSetError(form, input, val.length >= 2 ? "" : "Please enter your message.");
    }
  }

  function contactValidate(form) {
    form.setAttribute("data-tried", "true");
    var firstBad = null;
    var need = function (input, ok, message) {
      checkoutSetError(form, input, ok ? "" : message);
      if (!ok && !firstBad) {
        firstBad = input;
      }
      return ok;
    };
    var byId = function (id) {
      return document.getElementById(id);
    };
    var val = function (id) {
      var el = byId(id);
      return el ? el.value.trim() : "";
    };
    var ok = true;
    ok = need(byId("fd-contact-name"), val("fd-contact-name").length >= 2, "Please enter your name.") && ok;
    ok = need(byId("fd-contact-phone"), checkoutPhoneOk(val("fd-contact-phone")), "Please enter a valid Nigerian phone number.") && ok;
    var email = val("fd-contact-email");
    ok = need(byId("fd-contact-email"), !email || /^\S+@\S+\.\S+$/.test(email), "Please enter a valid email address.") && ok;
    ok = need(byId("fd-contact-subject"), val("fd-contact-subject").length >= 2, "Please enter a subject.") && ok;
    ok = need(byId("fd-contact-message"), val("fd-contact-message").length >= 2, "Please enter your message.") && ok;
    if (!ok && firstBad) {
      try {
        firstBad.focus();
      } catch (e) {
        /* focus is best-effort */
      }
    }
    return ok;
  }

  // WhatsApp handoff for a validated enquiry. Uses the single configured
  // number via the shared builder — the number never appears here.
  function contactWhatsAppHref(payload) {
    var lines = ["Hello Harvest Castle!"];
    lines.push("");
    lines.push("Name: " + payload.name);
    lines.push("Phone: " + payload.phone);
    if (payload.email) {
      lines.push("Email: " + payload.email);
    }
    lines.push("Subject: " + payload.subject);
    lines.push("");
    lines.push(payload.message);
    return buildLink(lines.join("\n"));
  }

  function contactFirstName(payload) {
    return payload.name ? String(payload.name).trim().split(/\s+/)[0] : "there";
  }

  function wireContact() {
    var form = document.getElementById("fd-contact-form");
    if (!form) {
      return;
    }
    var sendBtn = document.getElementById("fd-contact-send");

    // Gentle validation (same convention as checkout): blur validates only
    // after a first submit attempt; typing clears the field error at once.
    var fields = form.querySelectorAll("input, textarea");
    for (var f = 0; f < fields.length; f++) {
      (function (input) {
        input.addEventListener("blur", function () {
          if (form.getAttribute("data-tried") === "true" && !input.disabled) {
            contactValidateField(form, input);
          }
        });
        input.addEventListener("input", function () {
          checkoutSetError(form, input, "");
        });
      })(fields[f]);
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (!contactValidate(form)) {
        contactStatus("Please fix the highlighted fields.", true);
        return;
      }
      var payload = buildContactPayload();
      var result = submitContact(payload);
      if (result && result.status === "sent") {
        contactStatus("Thank you, " + contactFirstName(payload) + " — your message has been received. We will respond shortly.", false);
        form.reset();
        form.removeAttribute("data-tried");
        return;
      }
      if (result && result.status === "failed") {
        contactStatus("Something went wrong. Please try again or chat with us on WhatsApp.", true);
        return;
      }
      // No backend endpoint yet: hand the validated message to WhatsApp,
      // the established Harvest Castle channel. Nothing is claimed as sent
      // until the customer sends it there.
      window.open(contactWhatsAppHref(payload), "_blank", "noopener");
      contactStatus("Thank you, " + contactFirstName(payload) + " — your message is ready in WhatsApp. Press send there and we will respond shortly.", false);
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.removeAttribute("aria-disabled");
      }
    });
  }

  // Scroll-to-top progress ring. Enhances every .scrollToTop anchor in
  // place (no markup changes): an SVG ring fills with page-scroll
  // progress — empty at the top, a full circle at the bottom — and
  // shrinks back when scrolling up. Existing show/hide + click-to-top
  // behavior (main.js) is untouched; pages without the button no-op.
  function wireScrollProgress() {
    var buttons = document.querySelectorAll(".scrollToTop");
    if (!buttons.length) {
      return;
    }
    var SVG_NS = "http://www.w3.org/2000/svg";
    var bars = [];
    for (var i = 0; i < buttons.length; i++) {
      if (buttons[i].hasAttribute("data-fd-progress")) {
        continue;
      }
      buttons[i].setAttribute("data-fd-progress", "true");
      var svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("class", "fd-scroll-progress");
      svg.setAttribute("viewBox", "0 0 64 64");
      svg.setAttribute("aria-hidden", "true");
      var track = document.createElementNS(SVG_NS, "circle");
      track.setAttribute("class", "fd-scroll-progress-track");
      track.setAttribute("cx", "32");
      track.setAttribute("cy", "32");
      track.setAttribute("r", "29");
      var bar = document.createElementNS(SVG_NS, "circle");
      bar.setAttribute("class", "fd-scroll-progress-bar");
      bar.setAttribute("cx", "32");
      bar.setAttribute("cy", "32");
      bar.setAttribute("r", "29");
      bar.setAttribute("pathLength", "100");
      bar.setAttribute("stroke-dasharray", "100");
      bar.setAttribute("stroke-dashoffset", "100");
      svg.appendChild(track);
      svg.appendChild(bar);
      buttons[i].insertBefore(svg, buttons[i].firstChild);
      bars.push(bar);
    }
    if (!bars.length) {
      return;
    }
    var ticking = false;
    function paint() {
      ticking = false;
      var max =
        document.documentElement.scrollHeight - window.innerHeight;
      var y =
        window.pageYOffset || document.documentElement.scrollTop || 0;
      var p = max > 0 ? Math.min(1, Math.max(0, y / max)) : 0;
      var offset = String((100 - p * 100).toFixed(2));
      for (var k = 0; k < bars.length; k++) {
        bars[k].setAttribute("stroke-dashoffset", offset);
      }
    }
    function requestPaint() {
      if (ticking) {
        return;
      }
      ticking = true;
      if (window.requestAnimationFrame) {
        window.requestAnimationFrame(paint);
      } else {
        paint();
      }
    }
    window.addEventListener("scroll", requestPaint, { passive: true });
    window.addEventListener("resize", requestPaint);
    paint();
  }

  // Minimal read-only cart bridge for page scripts that extend the
  // storefront (checkout). Same store, same line maths, no second cart.
  window.FreshDirectCart = window.FreshDirectCart || {
    load: cartLoad,
    valid: cartPageValid,
    media: cartPageMedia,
    product: function (id) {
      return FD_CATALOG[id] || null;
    },
    subtotal: cartSubtotal,
    lineTotal: fdLineTotal,
    qtyLabel: fdQtyLabel,
    isKg: fdIsKgItem,
    fmtNaira: fmtNaira,
    validate: cartValidateServer,
    apply: cartApplyServer,
    messages: cartServerMessages,
    reconcile: cartReconcile,
    refresh: function () {
      refreshBadges();
      renderCartPanel();
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      wireWhatsApp();
      wireYear();
      wireMenuA11y();
      wireCart();
      wireCardLinks();
      wireCategoryToggle();
      wireShopView();
      wirePDP();
      wireCartPage();
      wireCheckout();
      wireConfirmation();
      wireContact();
      wireScrollProgress();
    });
  } else {
    wireWhatsApp();
    wireYear();
    wireMenuA11y();
    wireCart();
    wireCardLinks();
    wireCategoryToggle();
    wireShopView();
    wirePDP();
    wireCartPage();
    wireCheckout();
    wireConfirmation();
    wireContact();
    wireScrollProgress();
  }
})();
