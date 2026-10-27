/* ==========================================================================
   O'Toosin Farms — Checkout page (checkout.html only)
   Uses the existing freshdirect_cart_v1 store through the small
   window.FreshDirectCart bridge. Delivery locations come from the shared
   window.FreshDirectDeliveryLocations boundary so checkout and the admin
   Settings page use the same identifiers and fees.

   The supported frontend flow validates the order, presents a review and
   hands off to the existing order-confirmation page with payment still
   unpaid. No payment is simulated and no provider is contacted here.
   ========================================================================== */
(function () {
  "use strict";

  var cart = window.FreshDirectCart;
  if (!cart) {
    return;
  }

  var locationsApi = window.FreshDirectDeliveryLocations || null;
  var routes = window.FD_ROUTES || {
    productDetails: "product-details.html",
    orderConfirmation: "order-confirmation.html",
  };
  var LAST_ORDER_KEY = "freshdirect_last_order";
  var lastSubtotal = 0;
  var lastOrder = null;
  var busy = false;
  var activeOption = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function setText(el, value) {
    if (el) {
      el.textContent = value;
    }
  }

  function valueOf(id) {
    var el = byId(id);
    return el ? String(el.value || "").trim() : "";
  }

  function receiveValue() {
    var checked = document.querySelector(
      'input[name="receive-method"]:checked'
    );
    return checked ? checked.value : "delivery";
  }

  function locationList() {
    if (!locationsApi || typeof locationsApi.getActiveDeliveryLocations !== "function") {
      return [];
    }
    try {
      return locationsApi.getActiveDeliveryLocations() || [];
    } catch (e) {
      return [];
    }
  }

  function findLocation(id) {
    var list = locationList();
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        return list[i];
      }
    }
    return null;
  }

  function selectedDeliveryLocation() {
    return findLocation(valueOf("oto-co-delivery-location"));
  }

  function findPickupLocation(id) {
    if (!locationsApi || typeof locationsApi.getPickupLocations !== "function") {
      return null;
    }
    var list;
    try {
      list = locationsApi.getPickupLocations() || [];
    } catch (e) {
      return null;
    }
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        return list[i];
      }
    }
    return null;
  }

  function selectedPickupId() {
    var checked = document.querySelector(
      'input[name="pickup-location"]:checked'
    );
    if (checked) {
      return checked.value;
    }
    var locations = locationsApi && locationsApi.getPickupLocations
      ? locationsApi.getPickupLocations()
      : [];
    return locations.length ? locations[0].id : "";
  }

  function selectedPickupLocation() {
    return findPickupLocation(selectedPickupId());
  }

  function priceText(location) {
    if (!location) {
      return "";
    }
    return cart.fmtNaira(location.fee);
  }

  function deliveryFee() {
    var method = receiveValue();
    if (method === "pickup") {
      return 0;
    }
    var location = selectedDeliveryLocation();
    if (!location) {
      return null;
    }
    return location.fee;
  }

  function orderTotal() {
    var fee = deliveryFee();
    return lastSubtotal + (fee === null ? 0 : fee);
  }

  function phoneOk(value) {
    var digits = String(value).replace(/[\s\-()]/g, "");
    return /^(\+?234|0)[789][01]\d{8}$/.test(digits);
  }

  function setError(input, message) {
    if (!input) {
      return;
    }
    var error = byId(input.id + "-error");
    if (!message) {
      input.removeAttribute("aria-invalid");
      input.removeAttribute("aria-describedby");
      if (error) {
        error.textContent = "";
        error.setAttribute("hidden", "");
      }
      return;
    }
    input.setAttribute("aria-invalid", "true");
    if (error) {
      error.textContent = message;
      error.removeAttribute("hidden");
      input.setAttribute("aria-describedby", error.id);
    }
  }

  function setGroupError(errorId, message) {
    var error = byId(errorId);
    if (!error) {
      return;
    }
    if (!message) {
      error.textContent = "";
      error.setAttribute("hidden", "");
      return;
    }
    error.textContent = message;
    error.removeAttribute("hidden");
  }

  function status(message, isError) {
    var box = byId("fd-checkout-status");
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

  function paymentSentence() {
    var method = receiveValue();
    var subtotal = cart.fmtNaira(lastSubtotal);
    if (method === "pickup") {
      var pickup = selectedPickupLocation();
      return (
        "Your order total is " + subtotal + " for your products, with no delivery fee. " +
        "Complete your order and payment securely at checkout. " +
        "Collect from " +
        (pickup ? pickup.name + ", " + pickup.address : "your selected pickup location") +
        "."
      );
    }
    var location = selectedDeliveryLocation();
    if (!location) {
      return (
        "Select a delivery location to see the delivery fee and the full order total."
      );
    }
    return (
      "Your order total is " + cart.fmtNaira(orderTotal()) + ": " + subtotal +
      " for your products plus " + cart.fmtNaira(location.fee) +
      " delivery to " + location.name +
      ". Complete your order and payment securely at checkout."
    );
  }

  function totalLabel() {
    var method = receiveValue();
    if (method === "pickup") {
      return "Order total";
    }
    var location = selectedDeliveryLocation();
    if (!location) {
      return "Products subtotal — select a location";
    }
    return "Order total";
  }

  function deliverySummary() {
    var method = receiveValue();
    if (method === "pickup") {
      return { label: "Delivery fee", value: "No delivery fee" };
    }
    var location = selectedDeliveryLocation();
    if (!location) {
      return { label: "Delivery fee", value: "Select a location" };
    }
    return {
      label:
        (location.type === "park" ? "Park delivery fee" : "Delivery fee") +
        " (" + location.name + ")",
      value: priceText(location),
    };
  }

  function updateTotals() {
    var subtotal = cart.fmtNaira(lastSubtotal);
    var subs = document.querySelectorAll("[data-checkout-subtotal]");
    for (var s = 0; s < subs.length; s++) {
      subs[s].textContent = subtotal;
    }
    var totals = document.querySelectorAll("[data-checkout-total]");
    var amount = cart.fmtNaira(orderTotal());
    for (var t = 0; t < totals.length; t++) {
      totals[t].textContent = amount;
    }
    setText(byId("oto-receive-name"), receiveValue() === "pickup" ? "Pickup" : "Delivery");
    var delivery = deliverySummary();
    setText(byId("oto-delivery-label"), delivery.label);
    setText(byId("oto-delivery-value"), delivery.value);
    setText(byId("oto-checkout-total-label"), totalLabel());
    setText(byId("oto-review-total-label"), totalLabel());
    var sentence = paymentSentence();
    setText(byId("oto-pay-note"), sentence);
    setText(byId("oto-pay-summary"), sentence);
    updateDeliverySelectionUI();
    if (lastOrder) {
      lastOrder.receive = buildReceive();
      lastOrder.deliveryFee = deliveryFee();
      lastOrder.total = orderTotal();
      lastOrder.payment = buildPayment();
      renderReviewPayment(lastOrder.payment);
    }
  }

  function productHref(item) {
    var product = cart.product ? cart.product(item.id) : null;
    return product && product.url
      ? product.url
      : routes.productDetails + "?id=" + encodeURIComponent(item.id);
  }

  function summaryItem(item) {
    var li = document.createElement("li");
    li.className = "oto-checkout-item";

    var media = cart.media(item);
    var thumb;
    if (media.src) {
      thumb = document.createElement("a");
      thumb.className = "oto-checkout-thumb";
      thumb.setAttribute("href", productHref(item));
      thumb.setAttribute("aria-label", "View " + item.name);
      var img = document.createElement("img");
      img.setAttribute("src", media.src);
      img.setAttribute("alt", media.alt || item.name);
      img.setAttribute("width", "56");
      img.setAttribute("height", "56");
      img.setAttribute("loading", "lazy");
      img.setAttribute("decoding", "async");
      thumb.appendChild(img);
    } else {
      thumb = document.createElement("span");
      thumb.className = "oto-checkout-thumb is-empty";
      thumb.setAttribute("aria-hidden", "true");
      thumb.textContent = String(item.name || "?").charAt(0).toUpperCase();
    }

    var copy = document.createElement("div");
    copy.className = "oto-checkout-item-copy";
    var name = document.createElement("strong");
    var nameLink = document.createElement("a");
    nameLink.setAttribute("href", productHref(item));
    nameLink.textContent = item.name;
    name.appendChild(nameLink);
    var meta = document.createElement("span");
    var isKg = cart.isKg(item);
    meta.textContent =
      cart.fmtNaira(item.price) + (isKg ? "/kg" : " each") +
      " \u00b7 " + cart.qtyLabel(item.qty, isKg);
    copy.appendChild(name);
    copy.appendChild(meta);

    var line = document.createElement("strong");
    line.className = "oto-checkout-item-total";
    line.textContent = cart.fmtNaira(cart.lineTotal(item.price, item.qty));

    li.appendChild(thumb);
    li.appendChild(copy);
    li.appendChild(line);
    return li;
  }

  function renderSummary() {
    var main = byId("oto-checkout-main");
    var empty = byId("oto-checkout-empty");
    var list = byId("oto-checkout-lines");
    if (!main || !empty || !list) {
      return false;
    }
    var items = cart.load();
    var valid = [];
    for (var i = 0; i < items.length; i++) {
      if (cart.valid(items[i])) {
        valid.push(items[i]);
      }
    }
    if (!valid.length) {
      main.setAttribute("hidden", "");
      empty.removeAttribute("hidden");
      lastSubtotal = 0;
      return false;
    }
    empty.setAttribute("hidden", "");
    main.removeAttribute("hidden");
    list.innerHTML = "";
    for (var j = 0; j < valid.length; j++) {
      list.appendChild(summaryItem(valid[j]));
    }
    lastSubtotal = cart.subtotal(valid);
    updateTotals();
    return true;
  }

  function currentItems() {
    var items = cart.load();
    var valid = [];
    for (var i = 0; i < items.length; i++) {
      if (cart.valid(items[i])) {
        valid.push(items[i]);
      }
    }
    return valid;
  }

  function buildReceive() {
    var method = receiveValue();
    if (method === "pickup") {
      var pickup = selectedPickupLocation();
      return {
        fulfilment: "pickup",
        method: "pickup",
        label: "Pickup",
        pickupLocation: pickup
          ? { id: pickup.id, name: pickup.name, address: pickup.address }
          : null,
      };
    }
    var location = selectedDeliveryLocation();
    var type = location ? location.type : "doorstep";
    var receive = {
      fulfilment: "delivery",
      method: type,
      type: type,
      label: "Delivery",
      locationId: location ? location.id : "",
      locationName: location ? location.name : "",
      location: location
        ? {
            id: location.id,
            type: location.type,
            name: location.name,
            areas: location.areas,
            city: location.city,
            state: location.state,
            fee: location.fee,
          }
        : null,
    };
    if (type === "doorstep" && location) {
      receive.zone = {
        name: location.name,
        areas: location.areas,
        fee: location.fee,
      };
    } else if (type === "park" && location) {
      receive.parkDestination = {
        name: location.name,
        fee: location.fee,
        instructions: location.instructions || "",
      };
    }
    return receive;
  }

  function buildPayment() {
    var method = receiveValue();
    var fee = deliveryFee();
    return {
      method: method,
      dueOnline: orderTotal(),
      deliveryFee: fee,
      feeConfirmed: true,
      confirmed: false,
      label: "Payment at checkout",
    };
  }

  function buildOrder() {
    var items = currentItems();
    if (!items.length) {
      return null;
    }
    var lines = [];
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var product = cart.product ? cart.product(item.id) : null;
      var media = cart.media(item);
      lines.push({
        productId: item.id,
        variantId: item.variantId || item.unit || item.variant || "",
        name: item.name,
        variantLabel: item.variant || item.unit || "",
        unit: item.unit || item.variant || "",
        category:
          item.category || (product && product.category) || "",
        condition:
          item.condition || (product && product.condition) || "",
        image: media.src || "",
        alt: media.alt || item.name,
        quantity: item.qty,
        quantityLabel: cart.qtyLabel(item.qty, cart.isKg(item)),
        unitPrice: item.price,
        lineTotal: cart.lineTotal(item.price, item.qty),
      });
    }
    var method = receiveValue();
    var location = method === "delivery" ? selectedDeliveryLocation() : null;
    var doorstep = method === "delivery" && location && location.type === "doorstep";
    return {
      customer: {
        name: valueOf("oto-co-name"),
        phone: valueOf("oto-co-phone"),
        email: valueOf("oto-co-email"),
      },
      delivery: {
        locationId: location ? location.id : "",
        locationName: location ? location.name : "",
        type: location ? location.type : "",
        address: doorstep ? valueOf("oto-co-address") : "",
        city: doorstep ? location.city || "" : "",
        state: doorstep ? location.state || "" : "",
        landmark: doorstep ? valueOf("oto-co-landmark") : "",
        instructions: valueOf("oto-co-notes"),
      },
      receive: buildReceive(),
      items: lines,
      subtotal: cart.subtotal(items),
      deliveryFee: deliveryFee(),
      total: orderTotal(),
      payment: buildPayment(),
      orderingMethod: "website",
    };
  }

  function checkField(input) {
    var id = input.id;
    var value = String(input.value || "").trim();
    var method = receiveValue();
    var message = "";
    if (id === "oto-co-name") {
      message = value.length >= 2 ? "" : "Please enter your full name.";
    } else if (id === "oto-co-phone") {
      message = phoneOk(value)
        ? ""
        : "Please enter a valid Nigerian phone number.";
    } else if (id === "oto-co-email") {
      message =
        !value || /^\S+@\S+\.\S+$/.test(value)
          ? ""
          : "Please enter a valid email address.";
    } else if (id === "oto-co-address") {
      var location = selectedDeliveryLocation();
      var needsAddress =
        method === "delivery" && location && location.type === "doorstep";
      if (!needsAddress) {
        message = "";
      } else {
        message =
          value.length >= 5
            ? ""
            : "Please enter your full delivery address.";
      }
    }
    setError(input, message);
    return !message;
  }

  function validateForm() {
    var form = byId("fd-checkout-form");
    var inputs = form
      ? form.querySelectorAll(
          "#oto-co-name, #oto-co-phone, #oto-co-email, #oto-co-address"
        )
      : [];
    var firstBad = null;
    for (var i = 0; i < inputs.length; i++) {
      if (!checkField(inputs[i]) && !firstBad) {
        firstBad = inputs[i];
      }
    }

    var method = receiveValue();
    var hiddenLocation = byId("oto-co-delivery-location");
    var trigger = byId("oto-loc-trigger");
    if (method === "delivery") {
      var location = selectedDeliveryLocation();
      if (!location) {
        setError(hiddenLocation, "Please select a delivery location.");
        if (trigger) {
          trigger.setAttribute("aria-invalid", "true");
        }
        if (!firstBad) {
          firstBad = trigger;
        }
      } else {
        setError(hiddenLocation, "");
        if (trigger) {
          trigger.removeAttribute("aria-invalid");
        }
      }
      setGroupError("oto-co-pickup-error", "");
    } else {
      setError(hiddenLocation, "");
      if (trigger) {
        trigger.removeAttribute("aria-invalid");
      }
      if (!selectedPickupId()) {
        setGroupError("oto-co-pickup-error", "Please select a pickup location.");
        if (!firstBad) {
          firstBad = byId("oto-pickup-options");
        }
      } else {
        setGroupError("oto-co-pickup-error", "");
      }
    }

    if (firstBad) {
      status("Please check the highlighted fields and try again.", true);
      try {
        firstBad.focus();
        firstBad.scrollIntoView({ block: "center", behavior: "smooth" });
      } catch (e) {
        /* focus is best-effort */
      }
      return null;
    }
    status("");
    return buildOrder();
  }

  function addReviewRow(container, label, value) {
    if (!value) {
      return;
    }
    var row = document.createElement("div");
    row.className = "oto-review-row";
    var dt = document.createElement("span");
    dt.className = "oto-review-label";
    dt.textContent = label;
    var dd = document.createElement("strong");
    dd.textContent = value;
    row.appendChild(dt);
    row.appendChild(dd);
    container.appendChild(row);
  }

  function renderReviewPayment(payment) {
    var box = byId("oto-review-payment");
    if (!box) {
      return;
    }
    box.innerHTML = "";
    var name = document.createElement("strong");
    name.textContent = payment.label || "Payment at checkout";
    var text = document.createElement("span");
    if (payment.method === "pickup") {
      text.textContent =
        "Your order total is " +
        cart.fmtNaira(payment.dueOnline) +
        " for your products, with no delivery fee. Complete your order and payment securely at checkout, then collect from the selected pickup location.";
    } else {
      text.textContent =
        "Your order total is " +
        cart.fmtNaira(payment.dueOnline) +
        ", including the applicable delivery fee. Complete your order and payment securely at checkout.";
    }
    box.appendChild(name);
    box.appendChild(text);
  }

  function renderReviewDetails(order) {
    var details = byId("oto-review-details");
    if (!details) {
      return;
    }
    details.innerHTML = "";
    addReviewRow(details, "Name", order.customer.name);
    addReviewRow(details, "Phone", order.customer.phone);
    addReviewRow(details, "Email", order.customer.email);
    addReviewRow(details, "Receiving method", order.receive.label);
    if (order.receive.fulfilment === "delivery") {
      addReviewRow(
        details,
        "Delivery type",
        order.receive.type === "park" ? "Park delivery" : "Doorstep delivery"
      );
      if (order.receive.location) {
        addReviewRow(
          details,
          "Delivery location",
          order.receive.location.name +
            (order.receive.type === "doorstep" && order.receive.location.areas
              ? " — " + order.receive.location.areas
              : "")
        );
      }
      if (order.receive.type === "doorstep") {
        addReviewRow(details, "Delivery address", order.delivery.address);
        addReviewRow(
          details,
          "City / state",
          [order.delivery.city, order.delivery.state].filter(Boolean).join(", ")
        );
        addReviewRow(details, "Landmark", order.delivery.landmark);
      } else {
        addReviewRow(
          details,
          "Park delivery fee",
          cart.fmtNaira(
            order.receive.location ? order.receive.location.fee : 0
          )
        );
      }
    } else if (order.receive.pickupLocation) {
      addReviewRow(
        details,
        "Pickup location",
        order.receive.pickupLocation.name
      );
      addReviewRow(
        details,
        "Pickup address",
        order.receive.pickupLocation.address
      );
    }
    addReviewRow(details, "Order notes", order.delivery.instructions);
  }

  function showReview(order) {
    if (!order) {
      return;
    }
    lastOrder = order;
    var items = byId("oto-review-items");
    if (!items) {
      return;
    }
    renderReviewDetails(order);
    items.innerHTML = "";
    for (var i = 0; i < order.items.length; i++) {
      var it = order.items[i];
      var li = document.createElement("li");
      var label = document.createElement("span");
      label.textContent = it.name + " \u00b7 " + it.quantityLabel;
      var amount = document.createElement("strong");
      amount.textContent = cart.fmtNaira(it.lineTotal);
      li.appendChild(label);
      li.appendChild(amount);
      items.appendChild(li);
    }
    updateTotals();
    renderReviewPayment(order.payment);

    var form = byId("fd-checkout-form");
    var review = byId("fd-checkout-review");
    if (form) {
      form.setAttribute("hidden", "");
    }
    if (review) {
      review.removeAttribute("hidden");
      var title = byId("oto-review-title");
      try {
        if (title) {
          title.focus({ preventScroll: true });
        }
        review.scrollIntoView({ block: "start", behavior: "smooth" });
      } catch (e) {
        /* focus/scroll is best-effort */
      }
    }
  }

  function editDetails() {
    var form = byId("fd-checkout-form");
    var review = byId("fd-checkout-review");
    if (form) {
      form.removeAttribute("hidden");
    }
    if (review) {
      review.setAttribute("hidden", "");
    }
    status("");
    var name = byId("oto-co-name");
    if (name) {
      try {
        form.scrollIntoView({ block: "start", behavior: "smooth" });
        name.focus({ preventScroll: true });
      } catch (e) {
        /* best-effort */
      }
    }
  }

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
    return "OF-" + out;
  }

  function saveOrderSnapshot(order) {
    var snapshot = {
      id: makeOrderRef(),
      status: "saved",
      placedAt: new Date().toISOString(),
      orderingMethod: "website",
      customer: order.customer,
      delivery: order.delivery,
      receive: order.receive,
      items: order.items,
      subtotal: order.subtotal,
      deliveryFee: order.deliveryFee,
      total: order.total,
      payment: {
        method: order.payment.method,
        label: order.payment.label,
        dueOnline: order.payment.dueOnline,
        deliveryFee: order.payment.deliveryFee,
        feeConfirmed: order.payment.feeConfirmed,
        confirmed: order.payment.confirmed,
        status: "unpaid",
        verified: false,
        provider: "",
        reference: "",
      },
    };
    try {
      window.sessionStorage.setItem(
        LAST_ORDER_KEY,
        JSON.stringify(snapshot)
      );
      return snapshot;
    } catch (e) {
      return null;
    }
  }

  function finishCheckout() {
    if (!lastOrder) {
      status("Please review your order details before continuing.", true);
      return;
    }
    if (busy) {
      return;
    }
    busy = true;
    var snapshot = saveOrderSnapshot(lastOrder);
    if (!snapshot) {
      busy = false;
      status(
        "We could not save your order summary in this browser. Please try again.",
        true
      );
      return;
    }
    window.location.href =
      routes.orderConfirmation + "?order=" + encodeURIComponent(snapshot.id);
  }

  function reviewOrder() {
    var form = byId("fd-checkout-form");
    if (form) {
      form.setAttribute("data-tried", "true");
    }
    if (!renderSummary()) {
      status("Your cart is empty. Add some products before checking out.", true);
      return;
    }
    var order = validateForm();
    if (!order) {
      return;
    }
    showReview(order);
    closeDropdown(false);
  }

  function cartCheckMessage(result) {
    if (result && result.errors && result.errors.length) {
      var first = result.errors[0];
      if (first && first.message) {
        return first.message;
      }
    }
    return "Some items in your cart are no longer available. Please review your cart and try again.";
  }

  function proceedToPayment() {
    if (busy) {
      return;
    }
    var form = byId("fd-checkout-form");
    if (form) {
      form.setAttribute("data-tried", "true");
    }
    if (!renderSummary()) {
      status("Your cart is empty. Add some products before checking out.", true);
      return;
    }

    var complete = function () {
      var order = validateForm();
      if (!order) {
        busy = false;
        return;
      }
      lastOrder = order;
      busy = false;
      finishCheckout();
    };

    if (typeof cart.validate !== "function") {
      complete();
      return;
    }

    busy = true;
    status("Checking availability and prices\u2026");
    cart
      .validate(cart.load(), true)
      .then(function (result) {
        if (!result) {
          busy = false;
          status(
            "We could not check stock and prices. Please check your connection and try again.",
            true
          );
          return;
        }
        if (!result.ok || !result.items || !result.items.length) {
          busy = false;
          status(cartCheckMessage(result), true);
          return;
        }
        if (typeof cart.apply === "function") {
          cart.apply(result);
        }
        renderSummary();
        complete();
      })
      .catch(function () {
        busy = false;
        status(
          "We could not check stock and prices. Please check your connection and try again.",
          true
        );
      });
  }

  /* ---------- Custom delivery location dropdown ---------- */
  function optionMeta(location) {
    if (location.type === "park") {
      var parts = ["Approved park destination"];
      if (location.city) {
        parts.push(location.city);
      }
      return parts.join(" \u00b7 ");
    }
    var bits = [];
    if (location.areas) {
      bits.push(location.areas);
    }
    if (location.city) {
      bits.push(location.city);
    }
    return bits.length ? bits.join(" \u00b7 ") : "Doorstep delivery in Abeokuta";
  }

  function buildGroup(type, headingText, locations) {
    var group = document.createElement("div");
    group.className = "oto-loc-group";
    group.setAttribute("role", "group");
    var headingId = "oto-loc-group-" + type;
    var heading = document.createElement("div");
    heading.className = "oto-loc-group-head";
    heading.id = headingId;
    heading.setAttribute("role", "presentation");
    heading.textContent = headingText;
    group.setAttribute("aria-labelledby", headingId);
    group.appendChild(heading);

    for (var i = 0; i < locations.length; i++) {
      var location = locations[i];
      var option = document.createElement("button");
      option.type = "button";
      option.className = "oto-loc-option";
      option.id = "oto-loc-option-" + location.id;
      option.setAttribute("role", "option");
      option.setAttribute("data-location-id", location.id);
      option.setAttribute(
        "aria-selected",
        location.id === valueOf("oto-co-delivery-location") ? "true" : "false"
      );

      var check = document.createElement("span");
      check.className = "oto-loc-check";
      check.setAttribute("aria-hidden", "true");
      var checkIcon = document.createElement("i");
      checkIcon.className = "fas fa-check";
      check.appendChild(checkIcon);

      var copy = document.createElement("span");
      copy.className = "oto-loc-option-copy";
      var name = document.createElement("span");
      name.className = "oto-loc-option-name";
      name.textContent = location.name;
      var meta = document.createElement("span");
      meta.className = "oto-loc-option-meta";
      meta.textContent = optionMeta(location);
      copy.appendChild(name);
      copy.appendChild(meta);

      var price = document.createElement("span");
      price.className = "oto-loc-option-price";
      price.textContent = priceText(location);

      option.appendChild(check);
      option.appendChild(copy);
      option.appendChild(price);
      option.addEventListener("click", function () {
        selectLocation(this.getAttribute("data-location-id"));
      });
      group.appendChild(option);
    }
    return group;
  }

  function locationSearchText(location) {
    return [
      location.name,
      location.areas,
      location.city,
      location.state,
      location.type === "park" ? "park delivery" : "doorstep delivery",
    ]
      .join(" ")
      .toLowerCase();
  }

  function filterLocations(locations, query) {
    var term = String(query || "").trim().toLowerCase();
    if (!term) {
      return locations;
    }
    return locations.filter(function (location) {
      return locationSearchText(location).indexOf(term) !== -1;
    });
  }

  function renderLocationDropdown(query) {
    var listbox = byId("oto-loc-listbox");
    if (!listbox) {
      return;
    }
    var search = byId("oto-loc-search");
    var term = query === undefined ? (search ? search.value : "") : query;
    var locations = filterLocations(locationList(), term);
    var doorstep = [];
    var park = [];
    for (var i = 0; i < locations.length; i++) {
      if (locations[i].type === "park") {
        park.push(locations[i]);
      } else {
        doorstep.push(locations[i]);
      }
    }
    listbox.innerHTML = "";
    if (!locations.length) {
      var empty = document.createElement("div");
      empty.className = "oto-loc-empty";
      empty.textContent = String(term).trim()
        ? "No locations found for \u201c" + String(term).trim() + "\u201d."
        : "No delivery locations are available.";
      listbox.appendChild(empty);
      updateDeliverySelectionUI();
      return;
    }
    if (doorstep.length) {
      listbox.appendChild(
        buildGroup("doorstep", "Doorstep delivery — Abeokuta", doorstep)
      );
    }
    if (park.length) {
      listbox.appendChild(
        buildGroup("park", "Park delivery — approved destinations", park)
      );
    }
    updateDeliverySelectionUI();
  }

  function updateDeliverySelectionUI() {
    var location = selectedDeliveryLocation();
    var name = byId("oto-loc-trigger-name");
    var meta = byId("oto-loc-trigger-meta");
    var price = byId("oto-loc-trigger-price");
    var doorstepName = byId("oto-doorstep-zone-name");
    var parkName = byId("oto-park-name");
    var parkFee = byId("oto-park-fee");
    var parkDetail = byId("oto-park-detail");
    var doorstepFields = byId("oto-doorstep-fields");
    var parkFields = byId("oto-park-fields");
    var options = document.querySelectorAll(".oto-loc-option");

    for (var i = 0; i < options.length; i++) {
      options[i].setAttribute(
        "aria-selected",
        location && options[i].getAttribute("data-location-id") === location.id
          ? "true"
          : "false"
      );
    }

    if (!location) {
      setText(name, "Select a delivery location");
      setText(meta, "Doorstep or park delivery");
      setText(price, "");
      if (doorstepFields) {
        doorstepFields.setAttribute("hidden", "");
      }
      if (parkFields) {
        parkFields.setAttribute("hidden", "");
      }
      return;
    }

    setText(name, location.name);
    setText(
      meta,
      location.type === "park"
        ? "Park delivery" + (location.city ? " \u00b7 " + location.city : "")
        : "Doorstep delivery" + (location.city ? " \u00b7 " + location.city : "")
    );
    setText(price, priceText(location));

    if (location.type === "doorstep") {
      if (doorstepFields) {
        doorstepFields.removeAttribute("hidden");
      }
      if (parkFields) {
        parkFields.setAttribute("hidden", "");
      }
      setText(doorstepName, location.name);
    } else {
      if (doorstepFields) {
        doorstepFields.setAttribute("hidden", "");
      }
      if (parkFields) {
        parkFields.removeAttribute("hidden");
      }
      setText(parkName, location.name);
      setText(parkFee, "Delivery fee: " + cart.fmtNaira(location.fee));
      setText(
        parkDetail,
        location.instructions ||
          "Park delivery is available to approved destinations. Delivery arrangements and any applicable park charge depend on the selected destination."
      );
    }
  }

  function setActiveOption(option) {
    if (activeOption) {
      activeOption.classList.remove("is-active");
    }
    activeOption = option;
    if (activeOption) {
      activeOption.classList.add("is-active");
    }
  }

  function visibleOptions() {
    return Array.prototype.slice.call(
      document.querySelectorAll("#oto-loc-listbox .oto-loc-option")
    );
  }

  function openDropdown() {
    var popup = byId("oto-loc-popup");
    var trigger = byId("oto-loc-trigger");
    var select = byId("oto-loc-select");
    if (!popup || !trigger || !select || receiveValue() !== "delivery") {
      return;
    }
    popup.removeAttribute("hidden");
    select.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    var search = byId("oto-loc-search");
    if (search) {
      search.value = "";
    }
    renderLocationDropdown("");
    setActiveOption(null);
    if (search) {
      try {
        search.focus({ preventScroll: true });
      } catch (e) {
        /* focus is best-effort */
      }
    }
  }

  function closeDropdown(returnFocus) {
    var popup = byId("oto-loc-popup");
    var trigger = byId("oto-loc-trigger");
    var select = byId("oto-loc-select");
    if (popup) {
      popup.setAttribute("hidden", "");
    }
    if (select) {
      select.classList.remove("is-open");
    }
    if (trigger) {
      trigger.setAttribute("aria-expanded", "false");
    }
    var search = byId("oto-loc-search");
    if (search) {
      search.value = "";
    }
    setActiveOption(null);
    if (returnFocus && trigger) {
      try {
        trigger.focus({ preventScroll: true });
      } catch (e) {
        /* focus is best-effort */
      }
    }
  }

  function selectLocation(id) {
    var location = findLocation(id);
    if (!location) {
      return;
    }
    var previous = selectedDeliveryLocation();
    var hidden = byId("oto-co-delivery-location");
    if (!hidden) {
      return;
    }
    if (previous && previous.type !== location.type) {
      var address = byId("oto-co-address");
      var landmark = byId("oto-co-landmark");
      if (address) {
        address.value = "";
        setError(address, "");
      }
      if (landmark) {
        landmark.value = "";
      }
    }
    hidden.value = location.id;
    setError(hidden, "");
    var trigger = byId("oto-loc-trigger");
    if (trigger) {
      trigger.removeAttribute("aria-invalid");
    }
    status("");
    updateDeliverySelectionUI();
    updateTotals();
    closeDropdown(true);
  }

  function wireLocationSelector() {
    var trigger = byId("oto-loc-trigger");
    var popup = byId("oto-loc-popup");
    var select = byId("oto-loc-select");
    if (!trigger || !popup || !select) {
      return;
    }
    trigger.addEventListener("click", function () {
      if (popup.hasAttribute("hidden")) {
        openDropdown();
      } else {
        closeDropdown(true);
      }
    });
    trigger.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        openDropdown();
      } else if (event.key === "Escape" && !popup.hasAttribute("hidden")) {
        event.preventDefault();
        closeDropdown(true);
      }
    });
    var search = byId("oto-loc-search");
    if (search) {
      search.addEventListener("input", function () {
        renderLocationDropdown(search.value);
        setActiveOption(null);
      });
    }
    popup.addEventListener("keydown", function (event) {
      var options = visibleOptions();
      if (event.target === search) {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          if (options.length) {
            var first =
              event.key === "ArrowDown"
                ? options[0]
                : options[options.length - 1];
            setActiveOption(first);
            first.focus();
          }
        } else if (event.key === "Escape") {
          event.preventDefault();
          closeDropdown(true);
        } else if (event.key === "Enter") {
          event.preventDefault();
        }
        return;
      }
      if (!options.length) {
        if (event.key === "Escape") {
          event.preventDefault();
          closeDropdown(true);
        }
        return;
      }
      var index = options.indexOf(document.activeElement);
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (index === -1) {
          setActiveOption(options[0]);
          options[0].focus();
        } else {
          var next = Math.min(index + 1, options.length - 1);
          setActiveOption(options[next]);
          options[next].focus();
        }
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (index === -1) {
          setActiveOption(options[options.length - 1]);
          options[options.length - 1].focus();
        } else {
          var prev = Math.max(index - 1, 0);
          setActiveOption(options[prev]);
          options[prev].focus();
        }
      } else if (event.key === "Home") {
        event.preventDefault();
        setActiveOption(options[0]);
        options[0].focus();
      } else if (event.key === "End") {
        event.preventDefault();
        setActiveOption(options[options.length - 1]);
        options[options.length - 1].focus();
      } else if (event.key === "Enter" || event.key === " ") {
        if (index !== -1) {
          event.preventDefault();
          selectLocation(options[index].getAttribute("data-location-id"));
        }
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeDropdown(true);
      } else if (event.key === "Tab") {
        closeDropdown(false);
      }
    });
    document.addEventListener("click", function (event) {
      if (!select.contains(event.target)) {
        closeDropdown(false);
      }
    });
    window.addEventListener("resize", function () {
      closeDropdown(false);
    });
  }

  function refreshLocations() {
    var selected = valueOf("oto-co-delivery-location");
    if (selected && !findLocation(selected)) {
      var hidden = byId("oto-co-delivery-location");
      if (hidden) {
        hidden.value = "";
      }
      var trigger = byId("oto-loc-trigger");
      if (trigger) {
        trigger.removeAttribute("aria-invalid");
      }
    }
    renderLocationDropdown();
    updateDeliverySelectionUI();
    updateTotals();
  }

  function renderPickupOptions() {
    var wrap = byId("oto-pickup-options");
    if (!wrap) {
      return;
    }
    var locations =
      locationsApi && locationsApi.getPickupLocations
        ? locationsApi.getPickupLocations()
        : [];
    wrap.innerHTML = "";
    for (var i = 0; i < locations.length; i++) {
      var location = locations[i];
      var label = document.createElement("label");
      label.className = "fd-check-radio oto-pickup-location";
      var input = document.createElement("input");
      input.type = "radio";
      input.name = "pickup-location";
      input.value = location.id;
      if (i === 0) {
        input.checked = true;
      }
      var copy = document.createElement("span");
      copy.className = "oto-pickup-copy";
      var name = document.createElement("strong");
      name.textContent = location.name;
      var address = document.createElement("small");
      address.textContent = location.address;
      copy.appendChild(name);
      copy.appendChild(address);
      var tick = document.createElement("span");
      tick.className = "oto-pickup-tick";
      tick.setAttribute("aria-hidden", "true");
      var tickIcon = document.createElement("i");
      tickIcon.className = "fas fa-check";
      tick.appendChild(tickIcon);
      label.appendChild(input);
      label.appendChild(copy);
      label.appendChild(tick);
      wrap.appendChild(label);
    }
  }

  function updatePanels() {
    var method = receiveValue();
    var delivery = byId("oto-delivery-panel");
    var pickup = byId("oto-pickup-panel");
    if (delivery) {
      if (method === "delivery") {
        delivery.removeAttribute("hidden");
      } else {
        delivery.setAttribute("hidden", "");
      }
    }
    if (pickup) {
      if (method === "pickup") {
        pickup.removeAttribute("hidden");
      } else {
        pickup.setAttribute("hidden", "");
      }
    }
    if (method !== "delivery") {
      setError(byId("oto-co-address"), "");
      var hidden = byId("oto-co-delivery-location");
      setError(hidden, "");
      var trigger = byId("oto-loc-trigger");
      if (trigger) {
        trigger.removeAttribute("aria-invalid");
      }
    }
    if (method !== "pickup") {
      setGroupError("oto-co-pickup-error", "");
    }
  }

  function wireForm() {
    var form = byId("fd-checkout-form");
    if (!form) {
      return;
    }
    var fields = form.querySelectorAll("input, select, textarea");
    for (var i = 0; i < fields.length; i++) {
      (function (input) {
        if (input.type === "radio" && input.name === "receive-method") {
          return;
        }
        if (input.type === "radio" && input.name === "pickup-location") {
          input.addEventListener("change", function () {
            setGroupError("oto-co-pickup-error", "");
            status("");
            updateTotals();
          });
          return;
        }
        if (input.type === "hidden") {
          return;
        }
        input.addEventListener("blur", function () {
          if (form.getAttribute("data-tried") === "true") {
            checkField(input);
          }
        });
        input.addEventListener("input", function () {
          setError(input, "");
          status("");
        });
        input.addEventListener("change", function () {
          setError(input, "");
          status("");
        });
      })(fields[i]);
    }

    var methods = form.querySelectorAll('input[name="receive-method"]');
    for (var m = 0; m < methods.length; m++) {
      methods[m].addEventListener("change", function () {
        status("");
        updatePanels();
        updateTotals();
      });
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      proceedToPayment();
    });

    var reviewBtn = byId("fd-review-order");
    if (reviewBtn) {
      reviewBtn.addEventListener("click", reviewOrder);
    }

    var edit = byId("fd-review-edit");
    if (edit) {
      edit.addEventListener("click", editDetails);
    }

    var confirmOrder = byId("fd-review-confirm");
    if (confirmOrder) {
      confirmOrder.addEventListener("click", function () {
        if (confirmOrder.disabled) {
          return;
        }
        confirmOrder.disabled = true;
        finishCheckout();
        confirmOrder.disabled = false;
      });
    }
  }

  function init() {
    var wrap = byId("oto-checkout-wrap");
    if (!wrap) {
      return;
    }
    cart.seedDemo();
    renderLocationDropdown();
    renderPickupOptions();
    updatePanels();
    renderSummary();
    wireForm();
    wireLocationSelector();
    updateTotals();

    window.addEventListener("pageshow", function () {
      renderSummary();
    });
    document.addEventListener("freshdirect:cart", function () {
      var review = byId("fd-checkout-review");
      var form = byId("fd-checkout-form");
      if (review && !review.hasAttribute("hidden")) {
        review.setAttribute("hidden", "");
        if (form) {
          form.removeAttribute("hidden");
        }
        status("");
      }
      renderSummary();
    });
    window.addEventListener("storage", function (ev) {
      if (!ev) {
        return;
      }
      if (ev.key === "freshdirect_cart_v1") {
        var review = byId("fd-checkout-review");
        var form = byId("fd-checkout-form");
        if (review && !review.hasAttribute("hidden")) {
          review.setAttribute("hidden", "");
          if (form) {
            form.removeAttribute("hidden");
          }
          status("");
        }
        renderSummary();
      }
      if (locationsApi && ev.key === locationsApi.storeKey) {
        refreshLocations();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
