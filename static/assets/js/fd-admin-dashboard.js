(function () {
  "use strict";

  var RECENT_LIMIT = 5;

  function byId(id) {
    return document.getElementById(id);
  }

  function ordersService() {
    return window.FreshDirectAdminOrders || null;
  }

  function productsService() {
    return window.FreshDirectAdminProducts || null;
  }

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

  function fmtNaira(value) {
    var svc = ordersService();
    if (svc && svc.formatNaira) {
      return svc.formatNaira(value);
    }
    var amount = Number(value);
    return "\u20A6" + (isFinite(amount) ? amount.toLocaleString("en-NG") : "0");
  }

  function fmtDate(value) {
    var svc = ordersService();
    if (svc && svc.formatDate) {
      return svc.formatDate(value);
    }
    var date = new Date(value);
    return isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
  }

  function setBusy(host, busy) {
    if (!host) {
      return;
    }
    if (busy) {
      host.setAttribute("aria-busy", "true");
    } else {
      host.removeAttribute("aria-busy");
    }
  }

  function card(icon, label, value, context) {
    return (
      '<li class="fd-dash-card">' +
      '<span class="fd-dash-card-icon" aria-hidden="true"><i class="' + icon + '"></i></span>' +
      '<span class="fd-dash-card-label">' + esc(label) + "</span>" +
      '<span class="fd-dash-card-value">' + esc(value) + "</span>" +
      '<span class="fd-dash-card-context">' + esc(context) + "</span>" +
      "</li>"
    );
  }

  function renderOverview(orders, catalogueCount, orderError, catalogueError) {
    var host = byId("fd-dash-cards");
    if (!host) {
      return;
    }
    var svc = ordersService();
    var total = orderError ? "\u2014" : String(orders.length);
    var pending = "\u2014";
    var verified = "\u2014";
    var outstanding = "\u2014";

    if (!orderError && svc) {
      pending = 0;
      verified = 0;
      outstanding = 0;
      for (var i = 0; i < orders.length; i++) {
        if (orders[i].status === "pending") {
          pending += 1;
        }
        if (svc.paymentMeta(orders[i]).key === "paid") {
          verified += 1;
        }
        if (svc.paymentNeedsAttention(orders[i])) {
          outstanding += 1;
        }
      }
      pending = String(pending);
      verified = String(verified);
      outstanding = String(outstanding);
    }

    var products = catalogueError ? "\u2014" : String(catalogueCount);
    host.innerHTML =
      card("fas fa-receipt", "Total orders", total, "Orders recorded in this browser.") +
      card("fas fa-clock", "Pending orders", pending, "Orders still open for follow-up.") +
      card("fas fa-check-circle", "Verified payments", verified, "Orders with a verified payment reference.") +
      card("fas fa-credit-card", "Payment outstanding", outstanding, "Unpaid, pending or unverified payments.") +
      card("fas fa-box", "Catalogue products", products, "Products in the current admin catalogue.");
    setBusy(host, false);
  }

  function renderEmptyRow(message) {
    return (
      '<tr><td colspan="7" class="fd-dash-empty-cell">' +
      esc(message) +
      "</td></tr>"
    );
  }

  function renderOrders(orders, orderError) {
    var body = byId("fd-dash-orders-body");
    var count = byId("fd-dash-orders-count");
    var wrap = byId("fd-dash-orders-wrap");
    if (!body) {
      return;
    }
    var svc = ordersService();

    if (orderError || !svc) {
      body.innerHTML = renderEmptyRow(
        "Orders could not be loaded. Use the Orders page to try again."
      );
      if (count) {
        count.textContent = "Order data is unavailable.";
      }
      if (wrap) {
        wrap.removeAttribute("aria-busy");
      }
      return;
    }

    if (!orders.length) {
      body.innerHTML = renderEmptyRow(
        "No orders recorded yet. Checkout summaries appear here after a customer finishes checkout in this browser."
      );
      if (count) {
        count.textContent = "No orders recorded yet.";
      }
      if (wrap) {
        wrap.removeAttribute("aria-busy");
      }
      return;
    }

    var rows = orders.slice(0, RECENT_LIMIT);
    var html = "";
    for (var i = 0; i < rows.length; i++) {
      var order = rows[i];
      var payment = svc.paymentMeta(order);
      var paymentMethod = svc.paymentMethodMeta(order);
      var status = svc.orderStatusMeta(order.status);
      var location = svc.deliveryLocation(order);
      var detailUrl = "admin-order.html?id=" + encodeURIComponent(order.id);
      var receiveDetail = location.detail
        ? '<span class="fd-dash-receive-note">' + esc(location.detail) + "</span>"
        : "";

      html +=
        "<tr>" +
        '<th scope="row"><a class="fd-dash-ref" href="' + detailUrl + '">' + esc(order.id) + "</a>" +
        '<span class="fd-dash-date">' + esc(fmtDate(order.placedAt)) + "</span></th>" +
        "<td>" + esc(order.customer.name || "Not provided") + "</td>" +
        '<td><span class="fd-dash-items">' + esc(svc.itemSummary(order) || "No item lines") + "</span></td>" +
        '<td><span class="fd-dash-receive"><span class="fd-dash-receive-method">' +
        esc(svc.deliveryLabel(order.delivery.mode)) + "</span>" +
        '<span class="fd-dash-receive-note">' + esc(location.label) + "</span>" +
        receiveDetail + "</span></td>" +
        '<td class="is-amount">' + esc(fmtNaira(order.total)) + "</td>" +
        '<td><span class="fd-dash-pay"><span class="fd-dash-pay-method">' +
        esc(paymentMethod.label) + "</span>" +
        '<span class="fd-dash-pay-state">' + esc(payment.label) + "</span></span></td>" +
        '<td><span class="fd-dash-pill ' + status.tone + '">' + esc(status.label) + "</span></td>" +
        "</tr>";
    }

    body.innerHTML = html;
    if (count) {
      count.textContent =
        orders.length > RECENT_LIMIT
          ? "Showing the " + RECENT_LIMIT + " most recent of " + orders.length + " orders."
          : "Showing " + orders.length + (orders.length === 1 ? " order." : " orders.");
    }
    if (wrap) {
      wrap.removeAttribute("aria-busy");
    }
  }

  function topGroup(category) {
    if (
      category === "Pork" ||
      category === "Chicken" ||
      category === "Turkey" ||
      category === "Beef" ||
      category === "Goat Meat"
    ) {
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

  function priceOf(product) {
    if (product && product.variants && product.variants.length) {
      var value = Number(product.variants[0].price);
      return isFinite(value) ? value : 0;
    }
    return 0;
  }

  function unitSuffix(product) {
    var unit = String((product && product.priceUnit) || "");
    return unit.indexOf("per ") === 0 ? "/" + unit.slice(4) : "";
  }

  function productMeta(product) {
    var category = String(product.category || "");
    var group = topGroup(category);
    var label = group === "Meats" ? "Meats \u00b7 " + category : category;
    if (product.group) {
      label += " \u00b7 " + product.group;
    }
    return (
      label +
      " \u00b7 " +
      fmtNaira(priceOf(product)) +
      unitSuffix(product)
    );
  }

  function renderProducts(catalogue, catalogueError) {
    var host = byId("fd-dash-products-list");
    var count = byId("fd-dash-products-count");
    if (!host) {
      return;
    }

    if (catalogueError) {
      host.innerHTML =
        '<li><div class="fd-dash-product-id"><strong>Product data is unavailable.</strong>' +
        "<span>Open the Products page to try again.</span></div></li>";
      if (count) {
        count.textContent = "Catalogue data is unavailable.";
      }
      setBusy(host, false);
      return;
    }

    var products = [];
    for (var id in catalogue) {
      if (Object.prototype.hasOwnProperty.call(catalogue, id)) {
        products.push(catalogue[id]);
      }
    }

    if (!products.length) {
      host.innerHTML =
        '<li><div class="fd-dash-product-id"><strong>No products recorded yet.</strong>' +
        "<span>Add a product to begin building the catalogue.</span></div></li>";
      if (count) {
        count.textContent = "No products in the catalogue yet.";
      }
      setBusy(host, false);
      return;
    }

    var groups = ["Meats", "Fish", "Live Animals", "Eggs", "Veggies", "Fruits"];
    var chosen = [];
    for (var g = 0; g < groups.length; g++) {
      for (var i = 0; i < products.length; i++) {
        if (topGroup(products[i].category) === groups[g]) {
          chosen.push(products[i]);
          break;
        }
      }
    }

    var html = "";
    for (var j = 0; j < chosen.length; j++) {
      var item = chosen[j];
      html +=
        "<li>" +
        '<div class="fd-dash-product-id"><strong>' + esc(item.name || "Unnamed product") + "</strong>" +
        "<span>" + esc(productMeta(item)) + "</span></div>" +
        '<span class="fd-dash-pill">' + esc(item.condition || "Available") + "</span>" +
        "</li>";
    }
    host.innerHTML = html;
    if (count) {
      count.textContent =
        "Showing " + chosen.length + " of " + products.length +
        (products.length === 1 ? " product" : " products") +
        ", one from each populated category.";
    }
    setBusy(host, false);
  }

  function init() {
    if (!byId("fd-dash-cards")) {
      return;
    }

    var orders = [];
    var catalogue = {};
    var orderError = false;
    var catalogueError = false;

    try {
      if (!ordersService()) {
        throw new Error("Order service unavailable");
      }
      orders = ordersService().getOrders() || [];
    } catch (e) {
      orderError = true;
    }

    try {
      if (!productsService()) {
        throw new Error("Product service unavailable");
      }
      catalogue = productsService().getCatalog() || {};
    } catch (e) {
      catalogueError = true;
    }

    renderOverview(
      orders,
      Object.keys(catalogue).length,
      orderError,
      catalogueError
    );
    renderOrders(orders, orderError);
    renderProducts(catalogue, catalogueError);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
