/* ==========================================================================
   O’TOOSIN Farms Admin — Orders list renderer
   --------------------------------------------------------------------------
   Vanilla JS, no dependencies, no framework. Admin-scoped: never touches
   the customer cart store or fresh-direct.js.

   Boundary:
     window.FreshDirectAdminOrders (fd-admin-orders-data.js) is the ONLY
     place this UI meets order data. Every number, row and summary on the
     page is derived from getOrders() — no hardcoded counts live in markup.
     Django stage: the service internals become API calls with the same
     signatures; every render*() function below is reused untouched.

   Manual QA scenario (?mock=error on admin-orders.html):
     forces the loading-error state to verify the retry path.
   ========================================================================== */
(function () {
  "use strict";

  var PAGE_SIZE = 8;

  function svc() {
    return window.FreshDirectAdminOrders || null;
  }

  function esc(text) {
    var s = svc();
    if (s && s.escape) {
      return s.escape(text);
    }
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
    var s = svc();
    if (s && s.formatNaira) {
      return s.formatNaira(n);
    }
    return "\u20A6" + Number(n).toLocaleString("en-NG");
  }

  function fmtDate(iso) {
    var s = svc();
    if (s && s.formatDate) {
      return s.formatDate(iso);
    }
    var d = new Date(iso);
    return isNaN(d.getTime()) ? "Date unavailable" : d.toLocaleString();
  }

  function detailUrl(order) {
    return "admin-order.html?id=" + encodeURIComponent(order.id);
  }

  /* ---------- State ---------- */
  var state = {
    q: "",
    orderStatus: "all",
    paymentStatus: "all",
    delivery: "all",
    sort: "newest",
    page: 0
  };

  var allOrders = [];

  /* ---------- Matching ---------- */
  function matchesSearch(order) {
    if (!state.q) {
      return true;
    }
    var q = state.q;
    var location = svc().deliveryLocation(order);
    var hay = [
      order.id,
      order.customer.name,
      order.customer.phone,
      order.customer.email,
      svc().itemSummary(order),
      svc().deliveryLabel(order.delivery.mode),
      location.label,
      location.detail
    ];
    for (var i = 0; i < hay.length; i++) {
      if ((hay[i] || "").toLowerCase().indexOf(q) !== -1) {
        return true;
      }
    }
    return false;
  }

  function matchesFilters(order) {
    var s = svc();
    if (state.orderStatus !== "all" && order.status !== state.orderStatus) {
      return false;
    }
    if (state.paymentStatus !== "all") {
      var key = s ? s.paymentMeta(order).key : "unpaid";
      if (key !== state.paymentStatus) {
        return false;
      }
    }
    if (state.delivery !== "all" && order.delivery.mode !== state.delivery) {
      return false;
    }
    return true;
  }

  function timeValue(order) {
    var t = new Date(order.placedAt).getTime();
    return isNaN(t) ? 0 : t;
  }

  function applySort(list) {
    var out = list.slice();
    if (state.sort === "oldest") {
      out.sort(function (a, b) {
        return timeValue(a) - timeValue(b);
      });
    } else if (state.sort === "total-desc") {
      out.sort(function (a, b) {
        return b.total - a.total;
      });
    } else if (state.sort === "total-asc") {
      out.sort(function (a, b) {
        return a.total - b.total;
      });
    } else {
      out.sort(function (a, b) {
        return timeValue(b) - timeValue(a);
      });
    }
    return out;
  }

  function visibleOrders() {
    var kept = [];
    for (var i = 0; i < allOrders.length; i++) {
      if (matchesSearch(allOrders[i]) && matchesFilters(allOrders[i])) {
        kept.push(allOrders[i]);
      }
    }
    return applySort(kept);
  }

  function isPristine() {
    return !!(
      !state.q &&
      state.orderStatus === "all" &&
      state.paymentStatus === "all" &&
      state.delivery === "all" &&
      state.sort === "newest"
    );
  }

  /* ---------- Renderers (pure UI; never compute business rules) ---------- */
  function pill(label, tone) {
    return (
      '<span class="fd-dash-pill' +
      (tone ? " " + tone : "") +
      '">' +
      esc(label) +
      "</span>"
    );
  }

  function renderSummary(orders) {
    var s = svc();
    var host = document.getElementById("fd-orders-cards");
    if (!host || !s) {
      return;
    }
    var pending = 0;
    var completed = 0;
    var outstanding = 0;
    for (var i = 0; i < orders.length; i++) {
      if (orders[i].status === "pending") {
        pending += 1;
      }
      if (orders[i].status === "completed") {
        completed += 1;
      }
      if (s.paymentNeedsAttention(orders[i])) {
        outstanding += 1;
      }
    }
    var cards = [
      {
        icon: "fas fa-receipt",
        label: "Total orders",
        value: String(orders.length),
        context: "Orders recorded across all fulfilment methods."
      },
      {
        icon: "fas fa-clock",
        label: "Pending orders",
        value: String(pending),
        context: "Orders still open for follow-up."
      },
      {
        icon: "fas fa-check-circle",
        label: "Completed",
        value: String(completed),
        context: "Orders marked completed."
      },
      {
        icon: "fas fa-credit-card",
        label: "Payment outstanding",
        value: String(outstanding),
        context: "Unpaid, pending or unverified payments."
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
    host.innerHTML = html;
  }

  function orderRow(order) {
    var s = svc();
    var ob = s.orderStatusMeta(order.status);
    var pb = s.paymentMeta(order);
    var location = s.deliveryLocation(order);
    var tr = document.createElement("tr");

    var refCell = document.createElement("th");
    refCell.setAttribute("scope", "row");
    refCell.setAttribute("data-label", "Order");
    var refLink = document.createElement("a");
    refLink.setAttribute("href", detailUrl(order));
    refLink.className = "fd-orders-ref";
    refLink.textContent = order.id;
    refCell.appendChild(refLink);
    var date = document.createElement("span");
    date.className = "fd-orders-date";
    date.textContent = fmtDate(order.placedAt);
    refCell.appendChild(date);
    tr.appendChild(refCell);

    var cust = document.createElement("td");
    cust.setAttribute("data-label", "Customer");
    var custName = document.createElement("strong");
    custName.className = "fd-orders-cust";
    custName.textContent = order.customer.name || "Not provided";
    cust.appendChild(custName);
    var phone = document.createElement("span");
    phone.className = "fd-orders-sub";
    phone.textContent = order.customer.phone || "Phone not provided";
    cust.appendChild(phone);
    tr.appendChild(cust);

    var items = document.createElement("td");
    items.setAttribute("data-label", "Items");
    var itemText = document.createElement("span");
    itemText.className = "fd-orders-items";
    itemText.textContent = s.itemSummary(order) || "No item lines";
    items.appendChild(itemText);
    tr.appendChild(items);

    var fulfil = document.createElement("td");
    fulfil.setAttribute("data-label", "Fulfilment");
    var receive = document.createElement("span");
    receive.className = "fd-orders-receive";
    var receiveMethod = document.createElement("strong");
    receiveMethod.className = "fd-orders-receive-method";
    receiveMethod.textContent = s.deliveryLabel(order.delivery.mode);
    receive.appendChild(receiveMethod);
    var receivePlace = document.createElement("span");
    receivePlace.className = "fd-orders-receive-place";
    receivePlace.textContent = location.label;
    receive.appendChild(receivePlace);
    if (location.detail) {
      var receiveDetail = document.createElement("span");
      receiveDetail.className = "fd-orders-sub";
      receiveDetail.textContent = location.detail;
      receive.appendChild(receiveDetail);
    }
    fulfil.appendChild(receive);
    tr.appendChild(fulfil);

    var total = document.createElement("td");
    total.setAttribute("data-label", "Order total");
    total.className = "is-amount";
    total.textContent = fmtNaira(order.total);
    tr.appendChild(total);

    var pay = document.createElement("td");
    pay.setAttribute("data-label", "Payment");
    pay.innerHTML = pill(pb.label, pb.tone);
    tr.appendChild(pay);

    var ost = document.createElement("td");
    ost.setAttribute("data-label", "Order status");
    ost.innerHTML = pill(ob.label, ob.tone);
    tr.appendChild(ost);

    var act = document.createElement("td");
    act.setAttribute("data-label", "Action");
    var view = document.createElement("a");
    view.setAttribute("href", detailUrl(order));
    view.className = "fd-prod-btn";
    view.setAttribute("aria-label", "Open order " + order.id);
    view.innerHTML =
      '<i class="far fa-eye" aria-hidden="true"></i>Open';
    act.appendChild(view);
    tr.appendChild(act);

    return tr;
  }

  function renderPagination(total, pageCount) {
    var nav = document.getElementById("fd-orders-pagination");
    var info = document.getElementById("fd-orders-pageinfo");
    var prev = document.getElementById("fd-orders-prev");
    var next = document.getElementById("fd-orders-next");
    if (!nav || !info || !prev || !next) {
      return;
    }
    if (total <= PAGE_SIZE) {
      nav.setAttribute("hidden", "");
      return;
    }
    nav.removeAttribute("hidden");
    info.textContent = "Page " + (state.page + 1) + " of " + pageCount;
    prev.disabled = state.page === 0;
    next.disabled = state.page >= pageCount - 1;
  }

  function renderList() {
    var s = svc();
    if (!s) {
      return;
    }
    var list = visibleOrders();
    var count = document.getElementById("fd-orders-count");
    var tableWrap = document.getElementById("fd-orders-table-wrap");
    var tbody = document.getElementById("fd-orders-body");
    var emptyAll = document.getElementById("fd-orders-empty-all");
    var emptyFiltered = document.getElementById("fd-orders-empty-filtered");
    var pagination = document.getElementById("fd-orders-pagination");
    if (!tableWrap || !tbody || !emptyAll || !emptyFiltered) {
      return;
    }
    tbody.innerHTML = "";
    if (!list.length) {
      if (pagination) {
        pagination.setAttribute("hidden", "");
      }
      if (count) {
        count.textContent = allOrders.length ? "" : "No orders recorded.";
      }
      if (!allOrders.length) {
        tableWrap.setAttribute("hidden", "");
        emptyFiltered.setAttribute("hidden", "");
        emptyAll.removeAttribute("hidden");
      } else {
        emptyAll.setAttribute("hidden", "");
        tableWrap.setAttribute("hidden", "");
        emptyFiltered.removeAttribute("hidden");
      }
      updateClearButton();
      return;
    }

    var pageCount = Math.ceil(list.length / PAGE_SIZE);
    if (state.page >= pageCount) {
      state.page = pageCount - 1;
    }
    var start = state.page * PAGE_SIZE;
    var pageItems = list.slice(start, start + PAGE_SIZE);

    if (count) {
      var end = start + pageItems.length;
      count.textContent =
        "Showing " +
        (start + 1) +
        "\u2013" +
        end +
        " of " +
        list.length +
        " orders" +
        (list.length === allOrders.length ? "" : " (filtered)") +
        ".";
    }
    emptyAll.setAttribute("hidden", "");
    emptyFiltered.setAttribute("hidden", "");
    tableWrap.removeAttribute("hidden");
    for (var i = 0; i < pageItems.length; i++) {
      tbody.appendChild(orderRow(pageItems[i]));
    }
    renderPagination(list.length, pageCount);
    updateClearButton();
  }

  function updateClearButton() {
    var clear = document.getElementById("fd-orders-clear");
    if (!clear) {
      return;
    }
    if (isPristine()) {
      clear.setAttribute("disabled", "");
    } else {
      clear.removeAttribute("disabled");
    }
  }

  /* ---------- Page states ---------- */
  function showLoading(on) {
    var loading = document.getElementById("fd-orders-loading");
    var content = document.getElementById("fd-orders-content");
    var error = document.getElementById("fd-orders-error");
    if (loading) {
      if (on) {
        loading.removeAttribute("hidden");
      } else {
        loading.setAttribute("hidden", "");
      }
    }
    if (content) {
      content.setAttribute("aria-busy", on ? "true" : "false");
    }
    if (on && error) {
      error.setAttribute("hidden", "");
    }
  }

  function showError() {
    var loading = document.getElementById("fd-orders-loading");
    var content = document.getElementById("fd-orders-content");
    var error = document.getElementById("fd-orders-error");
    if (loading) {
      loading.setAttribute("hidden", "");
    }
    if (content) {
      content.setAttribute("hidden", "");
    }
    if (error) {
      error.removeAttribute("hidden");
      var retry = document.getElementById("fd-orders-retry");
      if (retry) {
        retry.focus();
      }
    }
  }

  function readScenario() {
    try {
      var params = new URLSearchParams(window.location.search);
      return params.get("mock") === "error" ? "error" : "normal";
    } catch (e) {
      return "normal";
    }
  }

  function load() {
    var s = svc();
    if (!s) {
      showLoading(false);
      showError();
      return;
    }
    if (readScenario() === "error") {
      showLoading(false);
      showError();
      return;
    }
    showLoading(true);
    var orders;
    try {
      orders = s.getOrders();
    } catch (e) {
      showLoading(false);
      showError();
      return;
    }
    showLoading(false);
    allOrders = orders;
    var content = document.getElementById("fd-orders-content");
    if (content) {
      content.removeAttribute("hidden");
    }
    renderSummary(allOrders);
    renderList();
  }

  /* ---------- Controls ---------- */
  function resetControls() {
    state.q = "";
    state.orderStatus = "all";
    state.paymentStatus = "all";
    state.delivery = "all";
    state.sort = "newest";
    state.page = 0;
    var search = document.getElementById("fd-orders-search");
    var os = document.getElementById("fd-orders-status");
    var ps = document.getElementById("fd-orders-payment");
    var dm = document.getElementById("fd-orders-delivery");
    var sort = document.getElementById("fd-orders-sort");
    if (search) {
      search.value = "";
    }
    if (os) {
      os.value = "all";
    }
    if (ps) {
      ps.value = "all";
    }
    if (dm) {
      dm.value = "all";
    }
    if (sort) {
      sort.value = "newest";
    }
    renderList();
    if (search) {
      search.focus();
    }
  }

  function wireControls() {
    var search = document.getElementById("fd-orders-search");
    var os = document.getElementById("fd-orders-status");
    var ps = document.getElementById("fd-orders-payment");
    var dm = document.getElementById("fd-orders-delivery");
    var sort = document.getElementById("fd-orders-sort");
    var clear = document.getElementById("fd-orders-clear");
    var resetEmpty = document.getElementById("fd-orders-reset-empty");
    var retry = document.getElementById("fd-orders-retry");
    var prev = document.getElementById("fd-orders-prev");
    var next = document.getElementById("fd-orders-next");
    var debounce = null;

    function change(apply) {
      state.page = 0;
      apply();
      renderList();
    }

    if (search) {
      search.addEventListener("input", function () {
        window.clearTimeout(debounce);
        debounce = window.setTimeout(function () {
          state.q = search.value.trim().toLowerCase();
          state.page = 0;
          renderList();
        }, 150);
      });
      search.addEventListener("search", function () {
        window.clearTimeout(debounce);
        state.q = search.value.trim().toLowerCase();
        state.page = 0;
        renderList();
      });
    }
    if (os) {
      os.addEventListener("change", function () {
        change(function () {
          state.orderStatus = os.value;
        });
      });
    }
    if (ps) {
      ps.addEventListener("change", function () {
        change(function () {
          state.paymentStatus = ps.value;
        });
      });
    }
    if (dm) {
      dm.addEventListener("change", function () {
        change(function () {
          state.delivery = dm.value;
        });
      });
    }
    if (sort) {
      sort.addEventListener("change", function () {
        change(function () {
          state.sort = sort.value;
        });
      });
    }
    if (prev) {
      prev.addEventListener("click", function () {
        if (state.page > 0) {
          state.page -= 1;
          renderList();
        }
      });
    }
    if (next) {
      next.addEventListener("click", function () {
        var pageCount = Math.ceil(visibleOrders().length / PAGE_SIZE);
        if (state.page < pageCount - 1) {
          state.page += 1;
          renderList();
        }
      });
    }
    if (clear) {
      clear.addEventListener("click", resetControls);
    }
    if (resetEmpty) {
      resetEmpty.addEventListener("click", resetControls);
    }
    if (retry) {
      retry.addEventListener("click", function () {
        var error = document.getElementById("fd-orders-error");
        var content = document.getElementById("fd-orders-content");
        if (error) {
          error.setAttribute("hidden", "");
        }
        if (content) {
          content.removeAttribute("hidden");
        }
        load();
      });
    }
  }

  function init() {
    if (!document.getElementById("fd-orders-content")) {
      return;
    }
    wireControls();
    load();
  }

  /* Testable seam: automated checks use these. */
  window.FreshDirectAdminOrderList = {
    load: load,
    visible: visibleOrders,
    reset: resetControls,
    state: state,
    pageSize: PAGE_SIZE
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
