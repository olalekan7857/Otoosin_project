/* ==========================================================================
   O'Toosin Farms — Order confirmation page (order-confirmation.html only)
   Reads the single order snapshot saved by checkout under
   sessionStorage "freshdirect_last_order". The URL carries only the order
   reference; no payment state is trusted from the URL. A missing, stale or
   malformed snapshot never renders a false success state.
   ========================================================================== */
(function () {
  "use strict";

  var LAST_ORDER_KEY = "freshdirect_last_order";

  function byId(id) {
    return document.getElementById(id);
  }

  function escText(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function fmtNaira(value) {
    if (window.FreshDirectCart && window.FreshDirectCart.fmtNaira) {
      return window.FreshDirectCart.fmtNaira(value);
    }
    return "\u20A6" + Math.round(Number(value) || 0).toLocaleString("en-NG");
  }

  function numberOrNull(value) {
    var n = Number(value);
    return isFinite(n) ? n : null;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  function readOrder() {
    var raw = null;
    try {
      raw = window.sessionStorage.getItem(LAST_ORDER_KEY);
    } catch (e) {
      return null;
    }
    if (!raw) {
      return null;
    }
    var order = null;
    try {
      order = JSON.parse(raw);
    } catch (e) {
      return null;
    }
    if (!order || typeof order.id !== "string" || !order.id) {
      return null;
    }
    if (!Array.isArray(order.items) || !order.items.length) {
      return null;
    }
    if (!order.receive || typeof order.receive.method !== "string") {
      return null;
    }
    if (
      order.receive.method !== "doorstep" &&
      order.receive.method !== "park" &&
      order.receive.method !== "pickup"
    ) {
      return null;
    }
    return order;
  }

  function urlOrderId() {
    try {
      var params = new URLSearchParams(window.location.search);
      return params.get("order");
    } catch (e) {
      return null;
    }
  }

  function formatDate(value) {
    if (!value) {
      return "";
    }
    var date = new Date(value);
    if (isNaN(date.getTime())) {
      return "";
    }
    try {
      return date.toLocaleString("en-NG", {
        day: "numeric",
        month: "long",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch (e) {
      return date.toDateString();
    }
  }

  function firstName(order) {
    var name =
      order && order.customer && order.customer.name
        ? String(order.customer.name).trim()
        : "";
    return name ? name.split(/\s+/)[0] : "";
  }

  function isKgLine(item) {
    return /kg/i.test(
      String(item.variantLabel || "") + " " + String(item.quantityLabel || "")
    );
  }

  function lineTotal(item) {
    var stored = numberOrNull(item.lineTotal);
    if (stored !== null) {
      return stored;
    }
    var price = numberOrNull(item.unitPrice);
    var qty = numberOrNull(item.quantity);
    return price !== null && qty !== null ? price * qty : null;
  }

  function subtotalOf(order) {
    var stored = numberOrNull(order.subtotal);
    if (stored !== null) {
      return stored;
    }
    var sum = 0;
    for (var i = 0; i < order.items.length; i++) {
      var line = lineTotal(order.items[i]);
      if (line === null) {
        return null;
      }
      sum += line;
    }
    return sum;
  }

  function feeOf(order) {
    if (order.receive.method === "pickup") {
      return 0;
    }
    if (order.receive.method === "park") {
      var parkFee = numberOrNull(order.deliveryFee);
      return parkFee !== null ? parkFee : null;
    }
    return numberOrNull(order.deliveryFee);
  }

  function totalOf(order, subtotal, fee) {
    var stored = numberOrNull(order.total);
    if (stored !== null) {
      return stored;
    }
    if (subtotal === null) {
      return null;
    }
    return fee === null ? subtotal : subtotal + fee;
  }

  function methodIcon(method) {
    if (method === "pickup") {
      return "fas fa-store";
    }
    if (method === "park") {
      return "fas fa-bus";
    }
    return "fas fa-motorcycle";
  }

  function methodTitle(method) {
    if (method === "pickup") {
      return "Pickup";
    }
    if (method === "park") {
      return "Park delivery";
    }
    return "Doorstep delivery";
  }

  function addRow(container, label, value) {
    if (value === undefined || value === null || value === "") {
      return;
    }
    var row = el("div", "oto-confirm-row");
    row.appendChild(el("span", "oto-confirm-row-label", label));
    row.appendChild(el("strong", "oto-confirm-row-value", value));
    container.appendChild(row);
  }

  function buildThumb(item) {
    var thumb = el("span", "oto-confirm-thumb");
    var src = escText(item.image);
    var fallback = function () {
      thumb.innerHTML = "";
      thumb.textContent = String(item.name || "?").charAt(0).toUpperCase();
      thumb.classList.add("is-empty");
    };
    if (src) {
      var img = document.createElement("img");
      img.alt = item.alt || item.name || "Ordered product";
      img.width = 64;
      img.height = 64;
      img.loading = "lazy";
      img.decoding = "async";
      img.onerror = fallback;
      img.src = src;
      thumb.appendChild(img);
    } else {
      fallback();
    }
    return thumb;
  }

  function buildItem(item) {
    var li = el("li", "oto-confirm-item");
    li.appendChild(buildThumb(item));

    var copy = el("div", "oto-confirm-item-copy");
    copy.appendChild(el("strong", "oto-confirm-item-name", item.name || "Product"));

    var tags = el("span", "oto-confirm-item-tags");
    if (item.category) {
      tags.appendChild(el("span", "oto-confirm-tag", item.category));
    }
    if (item.condition) {
      tags.appendChild(el("span", "oto-confirm-tag is-state", item.condition));
    }
    if (tags.childNodes.length) {
      copy.appendChild(tags);
    }

    var qty = el("span", "oto-confirm-item-qty");
    var qtyText = item.quantityLabel || String(item.quantity || "");
    qty.textContent = "Quantity: " + qtyText;
    var unitPrice = numberOrNull(item.unitPrice);
    if (unitPrice !== null) {
      qty.textContent +=
        " \u00b7 " + fmtNaira(unitPrice) + (isKgLine(item) ? "/kg" : " each");
    }
    copy.appendChild(qty);

    li.appendChild(copy);

    var total = lineTotal(item);
    li.appendChild(
      el(
        "strong",
        "oto-confirm-item-total",
        total === null ? "\u2014" : fmtNaira(total)
      )
    );
    return li;
  }

  function buildItems(order) {
    var list = el("ul", "oto-confirm-items");
    list.setAttribute("aria-label", "Items in this order");
    for (var i = 0; i < order.items.length; i++) {
      list.appendChild(buildItem(order.items[i]));
    }
    return list;
  }

  function buildReceiveRows(order, rows) {
    var receive = order.receive;
    var delivery = order.delivery || {};
    if (receive.method === "doorstep") {
      if (receive.zone) {
        addRow(
          rows,
          "Delivery zone",
          receive.zone.name +
            (receive.zone.areas ? " \u2014 " + receive.zone.areas : "")
        );
      }
      addRow(rows, "Delivery address", delivery.address);
      addRow(rows, "City / town", delivery.city);
      addRow(rows, "State", delivery.state);
      addRow(rows, "Landmark", delivery.landmark);
    } else if (receive.method === "park") {
      addRow(
        rows,
        "Destination",
        receive.parkDestination ? receive.parkDestination.name : ""
      );
      var parkFee =
        receive.parkDestination &&
        receive.parkDestination.fee !== null &&
        receive.parkDestination.fee !== undefined
          ? numberOrNull(receive.parkDestination.fee)
          : null;
      addRow(
        rows,
        "Park delivery fee",
        parkFee === null ? "\u2014" : fmtNaira(parkFee)
      );
      addRow(
        rows,
        "Destination note",
        receive.parkDestination ? receive.parkDestination.instructions : ""
      );
    } else {
      if (receive.pickupLocation) {
        addRow(rows, "Pickup location", receive.pickupLocation.name);
        addRow(rows, "Pickup address", receive.pickupLocation.address);
      }
    }
    addRow(rows, "Order notes", delivery.instructions);
  }

  function buildReceiveBlock(order) {
    var block = el("section", "oto-confirm-block");
    var heading = el("h2", "oto-confirm-block-title", "Delivery & pickup");
    block.appendChild(heading);

    var card = el("div", "oto-confirm-method");
    var icon = el("span", "oto-confirm-method-icon");
    var iconNode = document.createElement("i");
    iconNode.className = methodIcon(order.receive.method);
    iconNode.setAttribute("aria-hidden", "true");
    icon.appendChild(iconNode);

    var copy = el("div", "oto-confirm-method-copy");
    copy.appendChild(el("strong", null, methodTitle(order.receive.method)));
    copy.appendChild(
      el(
        "span",
        "oto-confirm-method-note",
        order.receive.method === "pickup"
          ? "No delivery fee. Collection details are shown below."
          : order.receive.method === "park"
            ? "Approved destination. The park delivery charge is confirmed before dispatch."
            : "Doorstep delivery is currently available in Abeokuta."
      )
    );

    var rows = el("div", "oto-confirm-rows");
    buildReceiveRows(order, rows);

    card.appendChild(icon);
    card.appendChild(copy);
    var details = el("div", "oto-confirm-method-details");
    if (rows.childNodes.length) {
      details.appendChild(rows);
      card.appendChild(details);
    }
    block.appendChild(card);
    return block;
  }

  function buildTotals(order) {
    var subtotal = subtotalOf(order);
    var fee = feeOf(order);
    var total = totalOf(order, subtotal, fee);
    var isPark = order.receive.method === "park";
    var isPickup = order.receive.method === "pickup";

    var aside = el("aside", "oto-confirm-summary");
    aside.setAttribute("aria-label", "Order totals");
    aside.appendChild(el("h2", "oto-confirm-block-title", "Order totals"));

    function summaryRow(label, value, isTotal) {
      var row = el("div", "oto-confirm-total-row" + (isTotal ? " is-total" : ""));
      row.appendChild(el("span", null, label));
      row.appendChild(el("strong", null, value));
      aside.appendChild(row);
    }

    summaryRow(
      "Products subtotal",
      subtotal === null ? "\u2014" : fmtNaira(subtotal)
    );

    if (isPickup) {
      summaryRow("Delivery fee", "No delivery fee");
    } else if (isPark) {
      summaryRow(
        "Park delivery fee",
        fee === null ? "\u2014" : fmtNaira(fee)
      );
    } else {
      summaryRow("Delivery fee", fee === null ? "\u2014" : fmtNaira(fee));
    }

    summaryRow(
      "Order total",
      total === null ? "\u2014" : fmtNaira(total),
      true
    );

    if (isPickup) {
      aside.appendChild(
        el(
          "p",
          "oto-confirm-summary-note",
          "Pickup orders do not include a delivery fee."
        )
      );
    }

    return aside;
  }

  function buildNextSteps(order) {
    var block = el("section", "oto-confirm-block");
    block.appendChild(el("h2", "oto-confirm-block-title", "Next steps"));

    var list = el("ol", "oto-confirm-steps");
    var steps = ["Keep your order reference handy for future enquiries."];

    if (order.receive.method === "pickup") {
      var location = order.receive.pickupLocation;
      steps.push(
        location
          ? "After O’TOOSIN Farms confirms the order, collect it from " + location.name + ", " + location.address + "."
          : "After O’TOOSIN Farms confirms the order, collect it from your selected pickup location."
      );
      steps.push("Bring your order reference when you collect.");
    } else if (order.receive.method === "park") {
      var destination = order.receive.parkDestination;
      steps.push(
        destination
          ? "The approved park and delivery charge for " + destination.name + " are confirmed before dispatch."
          : "The approved park and delivery charge for your destination are confirmed before dispatch."
      );
      steps.push("Check the destination and order notes above.");
    } else {
      steps.push("Delivery is arranged after O’TOOSIN Farms confirms the order.");
      steps.push("Check that the delivery address and phone number above are correct.");
      steps.push("Contact us if any delivery detail changes.");
    }

    steps.push("Use the Contact page if you need help with this order.");

    for (var i = 0; i < steps.length; i++) {
      list.appendChild(el("li", null, steps[i]));
    }
    block.appendChild(list);
    return block;
  }

  function buildActions() {
    var actions = el("div", "oto-confirm-actions");
    var shop = el("a", "vs-btn", "Continue Shopping");
    shop.setAttribute("href", "product.html");
    var contact = el("a", "fd-ghost-btn", "Contact Us");
    contact.setAttribute("href", "contact.html");
    var cart = el("a", "fd-ghost-btn", "View Cart");
    cart.setAttribute("href", "cart.html");
    actions.appendChild(shop);
    actions.appendChild(contact);
    actions.appendChild(cart);
    return actions;
  }

  function buildCard(order) {
    var card = el("article", "oto-confirm-card");

    var hero = el("header", "oto-confirm-hero");
    var icon = el("span", "oto-confirm-hero-icon");
    var iconNode = document.createElement("i");
    iconNode.className = "fas fa-check";
    iconNode.setAttribute("aria-hidden", "true");
    icon.appendChild(iconNode);

    var heroCopy = el("div", "oto-confirm-hero-copy");
    heroCopy.appendChild(el("span", "oto-confirm-badge", "Order details saved"));

    var name = firstName(order);
    heroCopy.appendChild(
      el("h2", null, name ? "Thank you, " + name : "Your order details are ready")
    );
    heroCopy.appendChild(
      el(
        "p",
        "oto-confirm-lead",
        "Your checkout details are ready below. Keep your order reference for future enquiries."
      )
    );

    var meta = el("dl", "oto-confirm-meta");
    var refRow = el("div", "oto-confirm-meta-row");
    refRow.appendChild(el("dt", null, "Order reference"));
    refRow.appendChild(el("dd", null, order.id));
    meta.appendChild(refRow);
    var date = formatDate(order.placedAt);
    if (date) {
      var dateRow = el("div", "oto-confirm-meta-row");
      dateRow.appendChild(el("dt", null, "Date"));
      dateRow.appendChild(el("dd", null, date));
      meta.appendChild(dateRow);
    }
    if (order.payment && order.payment.status !== "paid") {
      var payRow = el("div", "oto-confirm-meta-row");
      payRow.appendChild(el("dt", null, "Payment status"));
      payRow.appendChild(el("dd", null, "Pending"));
      meta.appendChild(payRow);
    }
    heroCopy.appendChild(meta);

    hero.appendChild(icon);
    hero.appendChild(heroCopy);
    card.appendChild(hero);

    var layout = el("div", "row g-4 g-xl-5");
    var mainCol = el("div", "col-lg-7");
    mainCol.appendChild(buildReceiveBlock(order));

    var itemsBlock = el("section", "oto-confirm-block");
    itemsBlock.appendChild(el("h2", "oto-confirm-block-title", "Your items"));
    itemsBlock.appendChild(buildItems(order));
    mainCol.appendChild(itemsBlock);
    mainCol.appendChild(buildNextSteps(order));

    var sideCol = el("div", "col-lg-5");
    sideCol.appendChild(buildTotals(order));
    sideCol.appendChild(buildActions());

    layout.appendChild(mainCol);
    layout.appendChild(sideCol);
    card.appendChild(layout);
    return card;
  }

  function buildFallback() {
    var box = el("div", "fd-shop-state oto-confirm-fallback");
    var icon = document.createElement("i");
    icon.className = "far fa-receipt";
    icon.setAttribute("aria-hidden", "true");
    box.appendChild(icon);
    box.appendChild(el("h2", null, "Order details unavailable"));
    box.appendChild(
      el(
        "p",
        null,
        "We could not find an order to display. The order details may have expired, or this page may have been opened directly."
      )
    );
    var actions = el("div", "oto-confirm-fallback-actions");
    var shop = el("a", "vs-btn", "Continue Shopping");
    shop.setAttribute("href", "product.html");
    var cart = el("a", "fd-ghost-btn", "Return to Cart");
    cart.setAttribute("href", "cart.html");
    actions.appendChild(shop);
    actions.appendChild(cart);
    box.appendChild(actions);
    return box;
  }

  function renderFallback() {
    var mount = byId("oto-confirm-state");
    if (!mount) {
      return;
    }
    mount.innerHTML = "";
    mount.appendChild(buildFallback());
    document.title = "Order details unavailable | O’TOOSIN Farms";
  }

  function renderOrder(order) {
    var mount = byId("oto-confirm-state");
    if (!mount) {
      return;
    }
    mount.innerHTML = "";
    mount.appendChild(buildCard(order));
    document.title = "Order " + order.id + " | O’TOOSIN Farms";
  }

  function init() {
    var wrap = byId("oto-confirm-wrap");
    if (!wrap) {
      return;
    }
    var order = readOrder();
    var urlId = urlOrderId();
    if (!order || !urlId || urlId !== order.id) {
      renderFallback();
      return;
    }
    renderOrder(order);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
