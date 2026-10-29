/* ==========================================================================
   O’TOOSIN Farms — server-rendered order confirmation cart cleanup.

   The server only emits data-clear-cart after it has verified a paid payment.
   This script is a convenience mirror cleanup: it runs once per order, clears
   only the cart that matches the purchased lines, and never touches newer
   lines. Retail checkout does not depend on this script succeeding.
   ========================================================================== */
(function () {
  "use strict";

  var CART_KEY = "freshdirect_cart_v1";
  var LAST_ORDER_KEY = "freshdirect_last_order";

  function readPayload() {
    var wrap = document.getElementById("oto-confirm-wrap");
    if (!wrap) {
      return null;
    }
    var raw = wrap.getAttribute("data-clear-cart") || "";
    if (!raw) {
      return null;
    }
    try {
      var payload = JSON.parse(raw);
      if (!payload || !payload.reference || !Array.isArray(payload.lines)) {
        return null;
      }
      return payload;
    } catch (e) {
      return null;
    }
  }

  function formatQty(value) {
    var number = Number(value);
    return isFinite(number) ? number.toFixed(2) : "";
  }

  function expectedByKey(payload) {
    var map = {};
    for (var i = 0; i < payload.lines.length; i++) {
      var line = payload.lines[i];
      if (line && line.key) {
        map[line.key] = formatQty(line.quantity);
      }
    }
    return map;
  }

  function loadCart() {
    try {
      var raw = window.localStorage.getItem(CART_KEY);
      var items = raw ? JSON.parse(raw) : [];
      return Array.isArray(items) ? items : [];
    } catch (e) {
      return null;
    }
  }

  function saveCart(items) {
    try {
      window.localStorage.setItem(CART_KEY, JSON.stringify(items));
    } catch (e) {
      return false;
    }
    try {
      document.dispatchEvent(new CustomEvent("freshdirect:cart"));
    } catch (e) {
      /* other surfaces still refresh on next load */
    }
    if (window.FreshDirectCart && typeof window.FreshDirectCart.refresh === "function") {
      try {
        window.FreshDirectCart.refresh();
      } catch (e) {
        /* best effort */
      }
    }
    return true;
  }

  function cleanup(payload) {
    var flagKey = "freshdirect_cart_cleared_" + payload.reference;
    try {
      if (window.localStorage.getItem(flagKey) === "1") {
        return;
      }
    } catch (e) {
      return;
    }

    var cart = loadCart();
    if (cart === null) {
      return;
    }
    var expected = expectedByKey(payload);
    var keys = Object.keys(expected);
    if (!keys.length) {
      return;
    }

    var sameCart = cart.length === keys.length;
    if (sameCart) {
      for (var i = 0; i < cart.length; i++) {
        var key = String(cart[i] && cart[i].key ? cart[i].key : "");
        if (!Object.prototype.hasOwnProperty.call(expected, key) ||
            formatQty(cart[i].qty) !== expected[key]) {
          sameCart = false;
          break;
        }
      }
    }

    var next;
    if (sameCart) {
      next = [];
    } else {
      next = [];
      for (var j = 0; j < cart.length; j++) {
        var item = cart[j];
        var itemKey = String(item && item.key ? item.key : "");
        var purchased = Object.prototype.hasOwnProperty.call(expected, itemKey) &&
          formatQty(item.qty) === expected[itemKey];
        if (!purchased) {
          next.push(item);
        }
      }
    }

    if (next.length !== cart.length) {
      if (!saveCart(next)) {
        return;
      }
    }
    try {
      window.localStorage.setItem(flagKey, "1");
    } catch (e) {
      /* the cart is already safe; the flag is only duplicate protection */
    }
    try {
      window.sessionStorage.removeItem(LAST_ORDER_KEY);
    } catch (e) {
      /* legacy snapshot cleanup is best effort */
    }
  }

  function init() {
    var payload = readPayload();
    if (payload) {
      cleanup(payload);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
