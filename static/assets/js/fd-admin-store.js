/* ==========================================================================
   O'Toosin Farms Admin — Local seller-data store
   --------------------------------------------------------------------------
   Vanilla JS, no dependencies, no framework. Admin-scoped: never touches
   the customer cart store or fresh-direct.js.

   What this is:
     The current persistence behind the admin UI. Products created or
     edited in the product editor are kept in this browser (localStorage)
     and merged over the built-in catalog, so the product list, the
     dashboard and the editor all see the same items — including items
     the seller just added. Everything the seller sees was genuinely
     stored by this store, so success states ("Product created") are
     truthful.

   What this is NOT:
     This is not a backend. Customer pages (Home, Shop, Product Details,
     Cart, Checkout) read the static storefront catalog and do not see
     items kept here. Image files are previewed locally only; the product
     record keeps the image reference while the file bytes stay on the
     seller's device.

   DJANGO INTEGRATION (later stage, no admin-UI rebuild needed):
     - Replace readAll()/writeAll() with API calls (GET product list,
       POST/PUT product payload) that resolve the SAME canonical entry
       shape { id, name, category, status, badge?, defaultVariant, desc,
       images[], variants[] }.
     - Keep getLocal()/upsert()/isLocal() signatures so every consumer
       (fd-admin-products-data.js, fd-admin-product-editor.js) is reused
       untouched.
     - Do NOT hardcode endpoint URLs here.
   ========================================================================== */
(function () {
  "use strict";

  var STORAGE_KEY = "freshdirect_admin_products_v1";

  function storage() {
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        return window.localStorage;
      }
    } catch (e) {
      /* Storage unavailable (private mode) — callers treat this as empty. */
    }
    return null;
  }

  /* Guards the overlay so a hand-edited or older stored value can never
     inject malformed products into the catalog. */
  function isValidEntry(entry) {
    if (!entry || typeof entry !== "object") {
      return false;
    }
    if (typeof entry.id !== "string" || !entry.id) {
      return false;
    }
    if (typeof entry.name !== "string" || !entry.name) {
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

  function readAll() {
    var store = storage();
    if (!store) {
      return {};
    }
    try {
      var raw = store.getItem(STORAGE_KEY);
      if (!raw) {
        return {};
      }
      var data = JSON.parse(raw);
      var saved = (data && data.products) || {};
      var out = {};
      var ids = Object.keys(saved);
      for (var i = 0; i < ids.length; i++) {
        if (isValidEntry(saved[ids[i]])) {
          out[ids[i]] = saved[ids[i]];
        }
      }
      return out;
    } catch (e) {
      return {};
    }
  }

  function writeAll(map) {
    var store = storage();
    if (!store) {
      return false;
    }
    try {
      store.setItem(STORAGE_KEY, JSON.stringify({ v: 1, products: map || {} }));
      return true;
    } catch (e) {
      return false;
    }
  }

  function upsert(entry) {
    if (!isValidEntry(entry)) {
      return false;
    }
    var map = readAll();
    map[entry.id] = entry;
    return writeAll(map);
  }

  function isLocal(id) {
    if (!id) {
      return false;
    }
    return !!readAll()[id];
  }

  if (typeof window !== "undefined") {
    window.FreshDirectAdminStore = {
      getLocal: readAll,
      upsert: upsert,
      isLocal: isLocal,
      key: STORAGE_KEY
    };
  }
})();
