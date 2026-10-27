/* ==========================================================================
   O’TOOSIN Farms Admin — Order source boundary (order management)
   --------------------------------------------------------------------------
   Vanilla JS, no dependencies, no framework. Admin-scoped: never touches
   the customer cart store and never loads fresh-direct.js, so customer
   state cannot leak into the admin area.

   CANONICAL ORDER SHAPE (from assets/js/otoosin-checkout.js):
     { id, status, placedAt,
       customer { name, phone, email },
       delivery { mode, address, city, state, landmark, instructions },
       receive { method, label, zone, parkDestination, pickupLocation },
       items [{ productId, variantId, name, variantLabel, unit, category,
                condition, image, alt, quantity, quantityLabel,
                unitPrice, lineTotal }],
       subtotal, total, deliveryFee, orderingMethod,
       payment { method, label, dueOnline, deliveryFee, confirmed,
                 reference, status, verified } }

   ORDER STATUS is separate from PAYMENT STATUS:
     order   -> pending | completed | cancelled
     payment -> unpaid | pending | paid | failed (+ UI-only "unverified")
   "Paid" is a payment state, never an order status. A payment is shown as
   Paid only when the snapshot itself carries payment.verified === true
   plus a provider reference. No payment is marked paid just because an
   order exists or checkout details were entered.

   CURRENT SOURCE (frontend-only phase):
     - Checkout saves one snapshot to sessionStorage
       ("freshdirect_last_order"). getOrders() imports that snapshot into
       localStorage ("freshdirect_admin_orders_v1") the first time it is
       seen, so orders placed in this browser appear here.
     - Imported snapshots are never rewritten: item prices and totals stay
       exactly as recorded at order time. An admin status change updates
       only the order status field.
     - updateOrderStatus() validates the status, persists it through this
       same store, reads it back, and reports the genuine result. Success
       means "saved in this browser" — never a database claim.

   DJANGO INTEGRATION (later stage, no order-UI rebuild needed):
     - Replace the bodies of getOrders()/getOrder()/updateOrderStatus()
       with API calls that accept/resolve the SAME canonical shape and the
       SAME payload { orderId, status }.
     - Keep the public signatures so the list/detail renderers are reused.

   WHATSAPP: the store number mirrors FRESH_DIRECT.whatsappNumber
   (assets/js/fresh-direct.js), which mirrors the future Django setting
   WHATSAPP_NUMBER. Keep the digits in sync; never add a second number.
   ========================================================================== */
(function () {
  "use strict";

  var STORE_KEY = "freshdirect_admin_orders_v1";
  var LAST_ORDER_KEY = "freshdirect_last_order";

  /* Central store number (digits only). A WhatsApp number saved on the
     Settings page wins; otherwise the shared customer config; otherwise
     the same digits as a last resort. */
  function storeNumber() {
    try {
      if (
        window.FreshDirectAdminSettings &&
        typeof window.FreshDirectAdminSettings.getWhatsAppNumber === "function"
      ) {
        var saved = window.FreshDirectAdminSettings.getWhatsAppNumber();
        if (saved) {
          return saved;
        }
      }
    } catch (e) {
      /* fall through to the shared config */
    }
    try {
      if (
        window.FRESH_DIRECT &&
        typeof window.FRESH_DIRECT.whatsappNumber === "string" &&
        window.FRESH_DIRECT.whatsappNumber
      ) {
        return window.FRESH_DIRECT.whatsappNumber;
      }
    } catch (e) {
      /* fall through to the mirrored digits */
    }
    return "2349011058873";
  }

  /* Order statuses genuinely supported by this frontend. There is no
     fulfilment pipeline yet (preparing/ready/dispatched), so no such
     states are invented. Legacy stored states are migrated below. */
  var ALLOWED_STATUSES = ["pending", "completed", "cancelled"];

  var LEGACY_ORDER_STATUS = {
    saved: "pending",
    submitted: "pending",
    pending: "pending",
    processing: "pending",
    confirmed: "pending",
    ready: "pending",
    paid: "completed",
    completed: "completed",
    cancelled: "cancelled",
    canceled: "cancelled",
    failed: "cancelled"
  };

  var RECEIVE_METHODS = ["doorstep", "park", "pickup"];

  /* ---------- Small local helpers (admin copies; no customer dep) ---------- */
  function esc(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[c];
    });
  }

  function fmtNaira(n) {
    var v = Number(n);
    if (!isFinite(v)) {
      v = 0;
    }
    return "\u20A6" + v.toLocaleString("en-NG");
  }

  function fmtDate(iso) {
    var d = new Date(iso);
    if (!iso || isNaN(d.getTime())) {
      return "Date unavailable";
    }
    return d.toLocaleString("en-NG", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit"
    });
  }

  function fmtDateFull(iso) {
    var d = new Date(iso);
    if (!iso || isNaN(d.getTime())) {
      return "Date unavailable";
    }
    return d.toLocaleString("en-NG", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit"
    });
  }

  function asText(value) {
    return typeof value === "string" ? value : "";
  }

  function asQty(value) {
    var n = parseFloat(value);
    return isFinite(n) && n > 0 ? n : 1;
  }

  function asMoney(value, fallback) {
    if (value === null || value === undefined || value === "") {
      return fallback;
    }
    var n = Number(value);
    if (isFinite(n) && n >= 0) {
      return n;
    }
    return fallback;
  }

  function fmtQty(value) {
    var n = Number(value);
    if (!isFinite(n)) {
      return String(value);
    }
    return String(Math.round(n * 100) / 100);
  }

  function cleanText(value) {
    return asText(value).replace(/^\s+|\s+$/g, "");
  }

  /* ---------- Storage ---------- */
  function localStore() {
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        return window.localStorage;
      }
    } catch (e) {
      /* private mode — callers treat this as unavailable */
    }
    return null;
  }

  function readStoreMap() {
    var store = localStore();
    if (!store) {
      return {};
    }
    try {
      var raw = store.getItem(STORE_KEY);
      if (!raw) {
        return {};
      }
      var data = JSON.parse(raw);
      var saved = (data && data.orders) || {};
      var out = {};
      var ids = Object.keys(saved);
      for (var i = 0; i < ids.length; i++) {
        var order = normalize(saved[ids[i]]);
        if (order) {
          out[order.id] = order;
        }
      }
      return out;
    } catch (e) {
      return {};
    }
  }

  function writeStoreMap(map) {
    var store = localStore();
    if (!store) {
      return false;
    }
    try {
      store.setItem(STORE_KEY, JSON.stringify({ v: 1, orders: map || {} }));
      return true;
    } catch (e) {
      return false;
    }
  }

  function readSessionOrder() {
    try {
      if (!window.sessionStorage) {
        return null;
      }
      var raw = window.sessionStorage.getItem(LAST_ORDER_KEY);
      if (!raw) {
        return null;
      }
      return normalize(JSON.parse(raw));
    } catch (e) {
      return null;
    }
  }

  /* ---------- Normalization (checkout snapshot -> canonical order) ----------
     Accepts the current checkout snapshot (receive.method doorway/park/
     pickup) and the older snapshot shape with only delivery fields. Also
     tolerates the legacy dashboard placeholder shape. Returns null for
     anything without an id + item lines. */
  function normalize(raw) {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    var id = asText(raw.id) || asText(raw.ref);
    if (!id) {
      return null;
    }
    var itemsRaw = Array.isArray(raw.items) ? raw.items : [];
    var items = [];
    for (var i = 0; i < itemsRaw.length; i++) {
      var line = normalizeLine(itemsRaw[i]);
      if (line) {
        items.push(line);
      }
    }
    if (!items.length) {
      return null;
    }

    var customer = { name: "", phone: "", email: "" };
    if (typeof raw.customer === "string") {
      customer.name = raw.customer;
    } else if (raw.customer && typeof raw.customer === "object") {
      customer.name = asText(raw.customer.name);
      customer.phone = asText(raw.customer.phone);
      customer.email = asText(raw.customer.email);
    }

    var d = raw.delivery && typeof raw.delivery === "object" ? raw.delivery : {};
    var delivery = {
      mode: "",
      address: asText(d.address),
      city: asText(d.city),
      state: asText(d.state),
      landmark: asText(d.landmark),
      instructions: asText(d.instructions)
    };
    var receive = normalizeReceive(raw.receive, d.mode, delivery);
    delivery.mode = receive.method;

    var linesTotal = 0;
    for (var j = 0; j < items.length; j++) {
      linesTotal += items[j].lineTotal;
    }
    var subtotal = asMoney(raw.subtotal, NaN);
    if (!isFinite(subtotal)) {
      subtotal = linesTotal;
    }

    /* Preserve the fee recorded with the order. Pickup can never carry a
       delivery fee. Park delivery is confirmed before dispatch and has no
       amount until then. Doorstep fees are recorded by zone at checkout. */
    var recordedFee = asMoney(raw.deliveryFee, NaN);
    if (
      !isFinite(recordedFee) &&
      raw.payment &&
      typeof raw.payment === "object"
    ) {
      recordedFee = asMoney(raw.payment.deliveryFee, NaN);
    }
    var deliveryFee = isFinite(recordedFee) ? recordedFee : null;
    if (receive.method === "pickup") {
      deliveryFee = 0;
    }

    /* The recorded total is the snapshot's own figure, never recalculated
       from today's catalog. A missing total falls back to subtotal + fee.
       Pickup totals must equal the product subtotal (no delivery fee). */
    var total = asMoney(raw.total, NaN);
    if (receive.method === "pickup") {
      total = subtotal;
    } else if (!isFinite(total)) {
      total = subtotal + (deliveryFee == null ? 0 : deliveryFee);
    }

    var payment = normalizePayment(raw, total, deliveryFee);

    var statusRaw = asText(raw.status) || asText(raw.orderStatus);
    var status = LEGACY_ORDER_STATUS[statusRaw] || "pending";

    return {
      id: id,
      status: status,
      placedAt: asText(raw.placedAt),
      customer: customer,
      delivery: delivery,
      receive: receive,
      items: items,
      subtotal: subtotal,
      total: total,
      deliveryFee: deliveryFee,
      orderingMethod:
        asText(raw.orderingMethod) === "website" ? "website" : "whatsapp",
      payment: payment
    };
  }

  function normalizeReceive(rawReceive, legacyMode, delivery) {
    var r =
      rawReceive && typeof rawReceive === "object" ? rawReceive : {};
    var method = asText(r.method);
    if (method === "address") {
      method = "doorstep";
    }
    if (RECEIVE_METHODS.indexOf(method) === -1) {
      var mode = asText(legacyMode);
      if (mode === "address") {
        mode = "doorstep";
      }
      if (RECEIVE_METHODS.indexOf(mode) !== -1) {
        method = mode;
      } else if (
        delivery &&
        (delivery.address || delivery.city || delivery.state)
      ) {
        method = "doorstep";
      } else {
        method = "";
      }
    }

    var zone = null;
    if (r.zone && typeof r.zone === "object") {
      zone = {
        name: asText(r.zone.name),
        areas: asText(r.zone.areas),
        fee: asMoney(r.zone.fee, null)
      };
    }

    var parkDestination = null;
    if (r.parkDestination && typeof r.parkDestination === "object") {
      parkDestination = { name: asText(r.parkDestination.name) };
    }

    var pickupLocation = null;
    if (r.pickupLocation && typeof r.pickupLocation === "object") {
      pickupLocation = {
        name: asText(r.pickupLocation.name),
        address: asText(r.pickupLocation.address)
      };
    }

    return {
      method: method,
      label: asText(r.label) || deliveryLabel(method),
      zone: zone,
      parkDestination: parkDestination,
      pickupLocation: pickupLocation
    };
  }

  function normalizePayment(raw, total, deliveryFee) {
    var source =
      raw.payment && typeof raw.payment === "object" ? raw.payment : {};
    var status = asText(source.status);
    var legacy = asText(raw.paymentStatus);
    if (["unpaid", "pending", "paid", "failed"].indexOf(status) === -1) {
      status =
        ["unpaid", "pending", "paid", "failed"].indexOf(legacy) !== -1
          ? legacy
          : "unpaid";
    }
    var method = cleanText(source.method);

    /* Legacy payment arrangements are no longer surfaced as wording. New
       checkout snapshots use receive.method. */
    if (method === "pay-now" || method === "pay-on-delivery") {
      method = "";
    }

    return {
      method: method,
      label: cleanText(source.label),
      provider: asText(source.provider),
      reference: asText(source.reference),
      status: status,
      verified: source.verified === true,
      dueOnline: asMoney(source.dueOnline, total),
      deliveryFee: asMoney(source.deliveryFee, deliveryFee),
      confirmed: source.confirmed === true
    };
  }

  /* One snapshot line. Prices are the recorded order-time figures — the
     catalog is never consulted, so a later price change cannot rewrite
     history. */
  function normalizeLine(raw) {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    var name = asText(raw.name);
    if (!name) {
      return null;
    }
    var quantity = asQty(raw.quantity != null ? raw.quantity : raw.qty);
    var unitPrice = asMoney(raw.unitPrice != null ? raw.unitPrice : raw.price, NaN);
    if (!isFinite(unitPrice)) {
      return null;
    }
    var lineTotal = asMoney(raw.lineTotal, NaN);
    if (!isFinite(lineTotal)) {
      lineTotal = Math.round(unitPrice * quantity);
    }
    var unit =
      cleanText(raw.unit) ||
      cleanText(raw.variantId) ||
      cleanText(raw.variant) ||
      cleanText(raw.variantLabel);
    var quantityLabel = cleanText(raw.quantityLabel);
    if (!quantityLabel) {
      quantityLabel = /kg/i.test(unit)
        ? fmtQty(quantity) + " kg"
        : fmtQty(quantity);
    }
    return {
      productId: asText(raw.productId != null ? raw.productId : raw.id),
      variantId: asText(raw.variantId != null ? raw.variantId : (raw.unit || raw.variant)),
      name: name,
      variantLabel: asText(raw.variantLabel != null ? raw.variantLabel : (raw.variant || raw.unit)),
      unit: unit,
      category: asText(raw.category),
      condition: asText(raw.condition),
      image: asText(raw.image),
      alt: asText(raw.alt) || name,
      quantity: quantity,
      quantityLabel: quantityLabel,
      unitPrice: unitPrice,
      lineTotal: lineTotal
    };
  }

  /* ---------- Status language ---------- */
  function orderStatusMeta(status) {
    if (status === "completed") {
      return { key: "completed", label: "Completed", tone: "is-ok" };
    }
    if (status === "cancelled") {
      return { key: "cancelled", label: "Cancelled", tone: "is-bad" };
    }
    return { key: "pending", label: "Pending", tone: "is-warn" };
  }

  /* Payment state is derived only from the payment snapshot. Order status
     never confers payment. "Unverified" is honest UI language for a
     snapshot that claims paid without a verified reference. */
  function paymentMeta(order) {
    var p = (order && order.payment) || {
      status: "unpaid",
      verified: false,
      reference: ""
    };
    if (
      p.verified === true &&
      p.reference &&
      p.status === "paid"
    ) {
      return { key: "paid", label: "Paid", tone: "is-ok" };
    }
    if (p.status === "paid") {
      return { key: "unverified", label: "Unverified", tone: "is-warn" };
    }
    if (p.status === "pending") {
      return { key: "pending", label: "Pending", tone: "is-warn" };
    }
    if (p.status === "failed") {
      return { key: "failed", label: "Failed", tone: "is-bad" };
    }
    return { key: "unpaid", label: "Unpaid", tone: "is-muted" };
  }

  function safePaymentLabel(payment) {
    var label = cleanText(payment && payment.label);
    if (/pay\s*now|pay\s*on\s*delivery|pay\s*online|pay\s*at\s*checkout/i.test(label)) {
      return "Payment not recorded";
    }
    return label || "Payment not recorded";
  }

  /* The recorded payment arrangement, kept separate from payment status.
     Delivery fees are never folded into the product amount. */
  function paymentMethodMeta(order) {
    var p = (order && order.payment) || {};
    var method = order && order.receive ? order.receive.method : "";
    var label = safePaymentLabel(p);
    if (method === "pickup") {
      return {
        key: "pickup",
        label: label,
        amountLabel: "Order amount recorded",
        detail:
          "No payment is collected on this page. Pickup orders have no delivery fee."
      };
    }
    if (method === "park") {
      return {
        key: "park",
        label: label,
        amountLabel: "Products amount recorded",
        detail:
          "No payment is collected on this page. The park delivery charge is confirmed before dispatch."
      };
    }
    if (method === "doorstep") {
      return {
        key: "doorstep",
        label: label,
        amountLabel: "Order amount recorded",
        detail:
          "No payment is collected on this page. Any doorstep delivery fee is included in the order total."
      };
    }
    return {
      key: "not-recorded",
      label: label,
      amountLabel: "Order amount recorded",
      detail:
        "No fulfilment or payment method was recorded with this order."
    };
  }

  function deliveryLabel(mode) {
    if (mode === "pickup") {
      return "Pickup";
    }
    if (mode === "park") {
      return "Park delivery";
    }
    if (mode === "doorstep" || mode === "address") {
      return "Doorstep delivery";
    }
    return "Fulfilment details";
  }

  /* Short destination/location for the list. The detail page renders the
     full saved address or pickup address. */
  function deliveryLocation(order) {
    var deliver = (order && order.delivery) || {};
    var receive = (order && order.receive) || {};
    if (receive.method === "pickup") {
      var location = receive.pickupLocation || {};
      return {
        label: location.name || "Pickup location not recorded",
        detail: location.address || ""
      };
    }
    if (receive.method === "park") {
      var destination = receive.parkDestination || {};
      return {
        label: destination.name || "Destination not recorded",
        detail: "Park delivery"
      };
    }
    var zone = receive.zone || {};
    var cityState = [deliver.city, deliver.state].filter(Boolean).join(", ");
    return {
      label:
        zone.name ||
        cityState ||
        deliver.address ||
        "Address not recorded",
      detail: zone.areas || ""
    };
  }

  function deliveryFeeMeta(order) {
    if (!order || order.receive.method === "pickup") {
      return { label: "No delivery fee", isAmount: false };
    }
    if (order.deliveryFee == null) {
      return { label: "Not recorded", isAmount: false };
    }
    return { label: fmtNaira(order.deliveryFee), isAmount: true };
  }

  /* Product-specific units come from the recorded order line, never from
     an assumption that every product is sold by kilogram. */
  function itemUnitMeta(item) {
    var source = cleanText(
      (item && (item.unit || item.variantLabel)) || ""
    );
    var lower = source.toLowerCase();
    if (/kg/.test(lower)) {
      return { label: "kg", priceSuffix: "/kg" };
    }
    if (/crate/.test(lower)) {
      return { label: "crate", priceSuffix: "/crate" };
    }
    if (/basket/.test(lower)) {
      return { label: "basket", priceSuffix: "/basket" };
    }
    if (/chicken/.test(lower)) {
      return { label: "chicken", priceSuffix: "/chicken" };
    }
    var per = /^per\s+(.+)$/i.exec(source);
    if (per) {
      return { label: per[1], priceSuffix: "/" + per[1] };
    }
    return {
      label: source || "unit",
      priceSuffix: source ? "/" + source : ""
    };
  }

  function itemQuantityValue(item) {
    var label = cleanText(item && item.quantityLabel);
    if (/kg$/i.test(label)) {
      return label.replace(/\s*kg$/i, "");
    }
    return label || fmtQty(item.quantity);
  }

  function itemQuantityLong(item) {
    var unit = itemUnitMeta(item);
    var value = itemQuantityValue(item);
    if (unit.label === "kg") {
      return value + " kg";
    }
    var plural =
      Number(value) > 1 && !/s$/i.test(unit.label)
        ? unit.label + "s"
        : unit.label;
    return value + " " + plural;
  }

  function itemSummary(order) {
    var items = (order && order.items) || [];
    var parts = [];
    for (var i = 0; i < items.length; i++) {
      if (i === 2) {
        parts.push("+" + (items.length - 2) + " more");
        break;
      }
      parts.push(items[i].name + " \u00d7 " + itemQuantityLong(items[i]));
    }
    return parts.join(" \u00b7 ");
  }

  function itemCount(order) {
    var n = 0;
    var items = (order && order.items) || [];
    for (var i = 0; i < items.length; i++) {
      n += items[i].quantity || 0;
    }
    return n;
  }

  /* An order needs attention while it is still pending. Completed and
     cancelled orders are terminal. */
  function needsAttention(order) {
    return !!order && order.status === "pending";
  }

  /* Payment is outstanding when no verified payment exists yet. */
  function paymentNeedsAttention(order) {
    var key = paymentMeta(order).key;
    return key === "unpaid" || key === "pending" || key === "unverified";
  }

  /* ---------- Public boundary ---------- */

  /* All orders, newest first. Imports the checkout session snapshot on
     first sight (without overwriting an admin-updated status). */
  function getOrders() {
    var map;
    try {
      map = readStoreMap();
    } catch (e) {
      var err = new Error("Order data could not be loaded.");
      err.code = "ORDERS_LOAD_FAILED";
      throw err;
    }
    var sessionOrder = readSessionOrder();
    if (sessionOrder && !map[sessionOrder.id]) {
      map[sessionOrder.id] = sessionOrder;
      try {
        writeStoreMap(map);
      } catch (e) {
        /* storage unavailable — the in-memory copy still renders */
      }
    }
    var list = [];
    var ids = Object.keys(map);
    for (var i = 0; i < ids.length; i++) {
      list.push(map[ids[i]]);
    }
    list.sort(function (a, b) {
      var ta = new Date(a.placedAt).getTime();
      var tb = new Date(b.placedAt).getTime();
      var na = isNaN(ta);
      var nb = isNaN(tb);
      if (na && nb) {
        return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
      }
      if (na) {
        return 1;
      }
      if (nb) {
        return -1;
      }
      return tb - ta;
    });
    return list;
  }

  function getOrder(id) {
    if (!id) {
      return null;
    }
    var orders = getOrders();
    for (var i = 0; i < orders.length; i++) {
      if (orders[i].id === id) {
        return orders[i];
      }
    }
    return null;
  }

  /* The backend-ready update payload. */
  function buildStatusPayload(id, status) {
    return { orderId: id, status: status };
  }

  /* Validate -> build payload -> persist through the order service.
     Only the order status field changes; payment, items and totals stay
     untouched. */
  function updateOrderStatus(id, status) {
    if (ALLOWED_STATUSES.indexOf(status) === -1) {
      return {
        ok: false,
        payload: null,
        order: null,
        error: {
          code: "INVALID_STATUS",
          message: "Choose a valid order status."
        }
      };
    }
    var map = readStoreMap();
    var sessionOrder = readSessionOrder();
    if (sessionOrder && !map[sessionOrder.id]) {
      map[sessionOrder.id] = sessionOrder;
    }
    if (!map[id]) {
      return {
        ok: false,
        payload: buildStatusPayload(id, status),
        order: null,
        error: {
          code: "NOT_FOUND",
          message: "That order could not be found. It may have been removed."
        }
      };
    }
    map[id].status = status;
    var saved = writeStoreMap(map);
    if (!saved) {
      return {
        ok: false,
        payload: buildStatusPayload(id, status),
        order: null,
        error: {
          code: "STORE_UNAVAILABLE",
          message: "The status could not be saved in this browser. Please try again."
        }
      };
    }
    var verify = readStoreMap()[id];
    if (!verify || verify.status !== status) {
      return {
        ok: false,
        payload: buildStatusPayload(id, status),
        order: null,
        error: {
          code: "STORE_UNAVAILABLE",
          message: "The status could not be saved in this browser. Please try again."
        }
      };
    }
    return {
      ok: true,
      payload: buildStatusPayload(id, status),
      order: verify,
      error: null
    };
  }

  /* Order-specific follow-up message through the central store number:
     reference + customer + recorded total + current status. No private
     delivery details are embedded in the prefilled text. */
  function getOrderWhatsAppHref(order) {
    var statusLabel = orderStatusMeta(order.status).label;
    var lines = [
      "Hello! Following up on O’TOOSIN Farms order " + order.id + ".",
      "",
      "Customer: " + (order.customer.name || "—"),
      "Items: " + itemSummary(order),
      "Order total: " + fmtNaira(order.total),
      "Status: " + statusLabel,
      "",
      "Please confirm the next step."
    ];
    return (
      "https://wa.me/" +
      storeNumber() +
      "?text=" +
      encodeURIComponent(lines.join("\n"))
    );
  }

  function getCustomerCallHref(order) {
    var phone = order && order.customer ? asText(order.customer.phone) : "";
    if (!phone) {
      return "";
    }
    var dial = phone.replace(/[^\d+]/g, "");
    if (!dial) {
      return "";
    }
    return "tel:" + dial;
  }

  if (typeof window !== "undefined") {
    window.FreshDirectAdminOrders = {
      source: "local-snapshot",
      sourceNote:
        "Checkout snapshots kept in this browser. Replace internals with Django order endpoints.",
      storeKey: STORE_KEY,
      allowedStatuses: ALLOWED_STATUSES.slice(),
      getOrders: getOrders,
      getOrder: getOrder,
      buildStatusPayload: buildStatusPayload,
      updateOrderStatus: updateOrderStatus,
      normalize: normalize,
      orderStatusMeta: orderStatusMeta,
      paymentMeta: paymentMeta,
      paymentMethodMeta: paymentMethodMeta,
      deliveryLabel: deliveryLabel,
      deliveryLocation: deliveryLocation,
      deliveryFeeMeta: deliveryFeeMeta,
      itemUnitMeta: itemUnitMeta,
      itemQuantityValue: itemQuantityValue,
      itemQuantityLong: itemQuantityLong,
      itemSummary: itemSummary,
      itemCount: itemCount,
      needsAttention: needsAttention,
      paymentNeedsAttention: paymentNeedsAttention,
      getOrderWhatsAppHref: getOrderWhatsAppHref,
      getCustomerCallHref: getCustomerCallHref,
      formatNaira: fmtNaira,
      formatDate: fmtDate,
      formatDateFull: fmtDateFull,
      escape: esc
    };
  }
})();
