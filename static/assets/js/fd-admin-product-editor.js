/* ==========================================================================
   O’TOOSIN Farms Admin — Product Editor
   --------------------------------------------------------------------------
   One page (admin-product-edit.html) serves both modes:
     Add  -> admin-product-edit.html            (no ?id=, or ?mode=new)
     Edit -> admin-product-edit.html?id=<id>    (stable catalogue ID)
   An unknown ?id= shows the product-not-found state and never creates a
   product silently.

   Product details are read through window.FreshDirectAdminProducts and
   saved through window.FreshDirectAdminStore. The store keeps changes in
   this browser and the product list reads the same store, so a successful
   save is real for this admin session. Uploaded images are read once in
   the browser, resized for storage and kept with the product record; no
   file bytes leave the device.
   ========================================================================== */
(function () {
  "use strict";

  /* Meat products keep their specific cut category (Pork, Chicken, …) so
     the storefront's meat filters and breadcrumbs stay intact. The other
     five marketplace categories are stored directly. */
  var CATEGORIES = [
    "Pork", "Chicken", "Turkey", "Beef", "Goat Meat",
    "Fish", "Live Animals", "Eggs", "Veggies", "Fruits"
  ];
  var CATEGORY_GROUP = {
    "Pork": "Meats",
    "Chicken": "Meats",
    "Turkey": "Meats",
    "Beef": "Meats",
    "Goat Meat": "Meats",
    "Fish": "Fish",
    "Live Animals": "Live Animals",
    "Eggs": "Eggs",
    "Veggies": "Veggies",
    "Fruits": "Fruits"
  };
  var CONDITIONS_BY_GROUP = {
    "Meats": ["Fresh", "Frozen", "Fried"],
    "Fish": ["Fresh", "Frozen", "Fried"],
    "Live Animals": ["Live"],
    "Eggs": ["Fresh"],
    "Veggies": ["Fresh"],
    "Fruits": ["Fresh"]
  };
  var ALL_CONDITIONS = ["Fresh", "Frozen", "Fried", "Live"];
  var UNITS = {
    "kg": {
      priceBasis: "Per kilogram",
      priceUnit: "per kg",
      variantId: "1kg",
      variantLabel: "1kg",
      suffix: "/ kg",
      priceLabel: "Price per kilogram (\u20A6)",
      priceHint: "Numbers only, for example 4800."
    },
    "crate": {
      priceBasis: "Per crate",
      priceUnit: "per crate",
      variantId: "1 crate",
      variantLabel: "1 crate",
      suffix: "/ crate",
      priceLabel: "Price per crate (\u20A6)",
      priceHint: "Numbers only, for example 3800."
    },
    "basket": {
      priceBasis: "Per basket",
      priceUnit: "per basket",
      variantId: "1 basket",
      variantLabel: "1 basket",
      suffix: "/ basket",
      priceLabel: "Price per basket (\u20A6)",
      priceHint: "Numbers only, for example 2500."
    },
    "chicken": {
      priceBasis: "Per chicken",
      priceUnit: "per chicken",
      variantId: "1 live chicken",
      variantLabel: "1 live chicken",
      suffix: "/ chicken",
      priceLabel: "Price per live chicken (\u20A6)",
      priceHint: "Numbers only, for example 9500."
    }
  };
  var DEFAULT_UNIT_BY_GROUP = {
    "Meats": "kg",
    "Fish": "kg",
    "Live Animals": "chicken",
    "Eggs": "crate",
    "Veggies": "basket",
    "Fruits": "basket"
  };
  var AVAILABILITY = ["in", "limited", "out"];
  var AVAILABILITY_LABELS = {
    "in": "Available",
    "limited": "Limited",
    "out": "Out of Stock"
  };
  var MAX_PRICE = 50000000;
  var NEW_ID_PREFIX = "demo-";

  var IMAGE_MAX_SIZE = 5 * 1024 * 1024;
  var IMAGE_MAX_LABEL = "5 MB";
  var IMAGE_MAX_DIMENSION = 1000;
  var IMAGE_QUALITY = 0.82;
  var IMAGE_ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
  var IMAGE_ACCEPTED_EXTS = ["png", "jpg", "jpeg", "webp", "gif"];

  var GROUP_BY_CATEGORY = {
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

  function fmtNaira(n) {
    return "\u20A6" + Number(n).toLocaleString("en-NG");
  }

  function trim(text) {
    return String(text == null ? "" : text).replace(/^\s+|\s+$/g, "");
  }

  /* The product record keeps availability in its existing `status` field
     (the value Inventory, the dashboard and the storefront already read).
     Older editor drafts used `status: "draft"` to mean hidden, so keep that
     legacy meaning when an availability value is not present. */
  function resolveAvailability(draft) {
    if (draft && Object.prototype.hasOwnProperty.call(draft, "availability")) {
      return AVAILABILITY.indexOf(draft.availability) !== -1
        ? draft.availability
        : "";
    }
    if (draft && draft.status === "draft") {
      return "out";
    }
    if (draft && draft.status === "published") {
      return "in";
    }
    if (draft && AVAILABILITY.indexOf(draft.status) !== -1) {
      return draft.status;
    }
    return "";
  }

  function availabilityLabel(status) {
    return AVAILABILITY_LABELS[status] || AVAILABILITY_LABELS.in;
  }

  function slugify(text) {
    var s = String(text || "").toLowerCase();
    s = s.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return s;
  }

  function el(id) {
    if (typeof document === "undefined") {
      return null;
    }
    return document.getElementById(id);
  }

  function formatFileSize(bytes) {
    var n = Number(bytes);
    if (!isFinite(n) || n < 0) {
      return "";
    }
    if (n < 1024) {
      return n + " B";
    }
    if (n < 1024 * 1024) {
      return (Math.round((n / 1024) * 10) / 10) + " KB";
    }
    return (Math.round((n / (1024 * 1024)) * 10) / 10) + " MB";
  }

  function validateImageFile(file) {
    if (!file) {
      return { ok: false, error: "empty" };
    }
    var type = String(file.type || "").toLowerCase();
    if (type) {
      if (IMAGE_ACCEPTED_TYPES.indexOf(type) === -1) {
        return { ok: false, error: "type" };
      }
    } else {
      var name = String(file.name || "").toLowerCase();
      var ext = name.indexOf(".") !== -1 ? name.split(".").pop() : "";
      if (IMAGE_ACCEPTED_EXTS.indexOf(ext) === -1) {
        return { ok: false, error: "type" };
      }
    }
    if (typeof file.size === "number" && file.size > IMAGE_MAX_SIZE) {
      return { ok: false, error: "too-large" };
    }
    if (typeof file.size === "number" && file.size <= 0) {
      return { ok: false, error: "empty" };
    }
    return { ok: true, error: "" };
  }

  function imageFileErrorText(code, fileName) {
    var name = fileName ? "“" + fileName + "” " : "That file ";
    if (code === "empty") {
      return "Choose an image file first.";
    }
    if (code === "type") {
      return name + "is not a supported image. Use PNG, JPEG, WebP or GIF.";
    }
    if (code === "too-large") {
      return name + "is larger than " + IMAGE_MAX_LABEL + ". Choose a smaller image.";
    }
    return name + "could not be read as an image. Try another file.";
  }

  function altFromFilename(name) {
    var base = String(name || "").replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
    base = trim(base);
    if (!base) {
      return "";
    }
    return base.charAt(0).toUpperCase() + base.slice(1);
  }

  /* Read the chosen file once and prepare a compact image for the product
     record. The original file is never sent anywhere. */
  function prepareImageFile(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () {
        reject({ code: "unreadable" });
      };
      reader.onload = function () {
        var image = new Image();
        image.onerror = function () {
          reject({ code: "unreadable" });
        };
        image.onload = function () {
          try {
            var naturalWidth = image.naturalWidth || 0;
            var naturalHeight = image.naturalHeight || 0;
            if (!naturalWidth || !naturalHeight) {
              reject({ code: "unreadable" });
              return;
            }
            var scale = Math.min(
              1,
              IMAGE_MAX_DIMENSION / Math.max(naturalWidth, naturalHeight)
            );
            var width = Math.max(1, Math.round(naturalWidth * scale));
            var height = Math.max(1, Math.round(naturalHeight * scale));
            var canvas = document.createElement("canvas");
            canvas.width = width;
            canvas.height = height;
            var context = canvas.getContext("2d");
            if (!context) {
              reject({ code: "unreadable" });
              return;
            }
            context.drawImage(image, 0, 0, width, height);
            var src = canvas.toDataURL("image/webp", IMAGE_QUALITY);
            if (!src || src.indexOf("data:image/") !== 0) {
              src = String(reader.result || "");
            }
            if (!src) {
              reject({ code: "unreadable" });
              return;
            }
            resolve({ src: src, width: width, height: height });
          } catch (e) {
            reject({ code: "unreadable" });
          }
        };
        image.src = String(reader.result || "");
      };
      reader.readAsDataURL(file);
    });
  }

  /* ==========================================================================
     Catalogue boundary
     ========================================================================== */
  function getCatalog() {
    var source =
      (typeof window !== "undefined" &&
        window.FreshDirectAdminProducts &&
        window.FreshDirectAdminProducts.getCatalog()) ||
      null;
    if (!source || typeof source !== "object" || !Object.keys(source).length) {
      var err = new Error("Product details could not be loaded.");
      err.code = "PRODUCTS_LOAD_FAILED";
      throw err;
    }
    return source;
  }

  function listKnownImages(catalog) {
    var out = [];
    var seen = [];
    var ids = Object.keys(catalog);
    for (var i = 0; i < ids.length; i++) {
      var images = (catalog[ids[i]] && catalog[ids[i]].images) || [];
      for (var j = 0; j < images.length; j++) {
        if (images[j] && images[j].src && seen.indexOf(images[j].src) === -1) {
          seen.push(images[j].src);
          out.push({
            src: images[j].src,
            alt: images[j].alt || "",
            w: images[j].w || 0,
            h: images[j].h || 0
          });
        }
      }
    }
    return out;
  }

  /* ==========================================================================
     Pure logic
     ========================================================================== */
  function parsePrice(raw) {
    var cleaned = String(raw == null ? "" : raw).replace(/[₦,\s]/g, "");
    if (!cleaned) {
      return { ok: false, value: 0, error: "empty" };
    }
    if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) {
      return { ok: false, value: 0, error: "malformed" };
    }
    var value = Number(cleaned);
    if (!isFinite(value) || value <= 0) {
      return { ok: false, value: 0, error: "non-positive" };
    }
    if (value > MAX_PRICE) {
      return { ok: false, value: 0, error: "too-large" };
    }
    return { ok: true, value: value, error: "" };
  }

  function priceErrorText(code, unitKey) {
    var meta = unitMeta(unitKey);
    var basis = meta.priceBasis.toLowerCase();
    if (code === "empty") {
      return "Enter a price (" + basis + ").";
    }
    if (code === "malformed") {
      return "Enter a valid amount using numbers only, for example 4800.";
    }
    if (code === "non-positive") {
      return "Enter a price above " + fmtNaira(0) + " (" + basis + ").";
    }
    return "That price looks unusually large — check it and try again.";
  }

  function productIdFromName(name, catalog) {
    var base = NEW_ID_PREFIX + (slugify(name) || "product");
    if (!catalog || !catalog[base]) {
      return base;
    }
    var n = 2;
    while (catalog[base + "-" + n]) {
      n++;
    }
    return base + "-" + n;
  }

  function groupForCategory(category) {
    return GROUP_BY_CATEGORY[category] || "";
  }

  function categoryGroup(category) {
    return CATEGORY_GROUP[category] || "";
  }

  function conditionsForCategory(category) {
    var group = categoryGroup(category);
    return (group && CONDITIONS_BY_GROUP[group]) || ALL_CONDITIONS;
  }

  function defaultUnitForCategory(category) {
    var group = categoryGroup(category);
    return (group && DEFAULT_UNIT_BY_GROUP[group]) || "kg";
  }

  function unitMeta(key) {
    return UNITS[key] || UNITS.kg;
  }

  function resolveUnitKey(entry) {
    if (!entry) {
      return "kg";
    }
    var priceUnit = trim(entry.priceUnit).toLowerCase();
    if (priceUnit.indexOf("crate") !== -1) {
      return "crate";
    }
    if (priceUnit.indexOf("basket") !== -1) {
      return "basket";
    }
    if (
      priceUnit.indexOf("chicken") !== -1 ||
      priceUnit.indexOf("animal") !== -1
    ) {
      return "chicken";
    }
    var variant = trim(entry.defaultVariant).toLowerCase();
    if (variant.indexOf("crate") !== -1) {
      return "crate";
    }
    if (variant.indexOf("basket") !== -1) {
      return "basket";
    }
    if (variant.indexOf("chicken") !== -1 || variant.indexOf("animal") !== -1) {
      return "chicken";
    }
    return "kg";
  }

  function validateProduct(draft, ctx) {
    var errors = [];
    var categories = (ctx && ctx.categories) || CATEGORIES;

    var name = trim(draft.name);
    if (!name) {
      errors.push({ target: "fd-ed-name", message: "Enter the product name." });
    } else if (name.length < 2 || name.length > 120) {
      errors.push({ target: "fd-ed-name", message: "Use between 2 and 120 characters for the product name." });
    }

    if (!trim(draft.category)) {
      errors.push({ target: "fd-ed-category", message: "Choose a category." });
    } else if (categories.indexOf(draft.category) === -1) {
      errors.push({ target: "fd-ed-category", message: "Choose a valid category from the list." });
    }

    var allowedConditions = conditionsForCategory(draft.category);
    if (!trim(draft.condition)) {
      errors.push({ target: "fd-ed-condition", message: "Choose a product condition." });
    } else if (allowedConditions.indexOf(draft.condition) === -1) {
      errors.push({
        target: "fd-ed-condition",
        message: "Choose " + allowedConditions.join(", ") + " for this category."
      });
    }

    if (!trim(draft.unit)) {
      errors.push({ target: "fd-ed-unit", message: "Choose a selling unit." });
    } else if (!UNITS[draft.unit]) {
      errors.push({ target: "fd-ed-unit", message: "Choose a valid selling unit." });
    }

    var cut = trim(draft.cut);
    if (cut.length > 160) {
      errors.push({ target: "fd-ed-cut", message: "Keep the cut or pack detail under 160 characters." });
    }

    var desc = trim(draft.desc);
    if (!desc) {
      errors.push({ target: "fd-ed-desc", message: "Enter the product description." });
    } else if (desc.length > 2000) {
      errors.push({ target: "fd-ed-desc", message: "Keep the description under 2000 characters." });
    }

    if (!trim(draft.imageSrc)) {
      errors.push({ target: "fd-ed-image-file", message: "Choose a farm image or upload an image." });
    }

    var alt = trim(draft.imageAlt);
    if (!alt) {
      errors.push({ target: "fd-ed-image-alt", message: "Describe the image for screen readers." });
    } else if (alt.length > 125) {
      errors.push({ target: "fd-ed-image-alt", message: "Keep the image description under 125 characters." });
    }

    var price = parsePrice(draft.price);
    if (!price.ok) {
      errors.push({ target: "fd-ed-price", message: priceErrorText(price.error, draft.unit) });
    }

    if (!resolveAvailability(draft)) {
      errors.push({ target: "fd-ed-availability", message: "Choose an availability status." });
    }

    return errors;
  }

  function buildPayload(draft, ctx) {
    var isCreate = !!(ctx && ctx.isCreate);
    var catalog = (ctx && ctx.catalog) || {};
    var original = (ctx && ctx.original) || null;
    var knownImages = (ctx && ctx.knownImages) || [];

    var name = trim(draft.name);
    var category = draft.category;
    var condition = draft.condition;
    var availability = resolveAvailability(draft) || "in";
    var id = isCreate ? productIdFromName(name, catalog) : original.id;
    var price = parsePrice(draft.price);
    var src = trim(draft.imageSrc);
    var w = 0;
    var h = 0;
    for (var i = 0; i < knownImages.length; i++) {
      if (knownImages[i].src === src) {
        w = knownImages[i].w || 0;
        h = knownImages[i].h || 0;
      }
    }
    if (!(w > 0 && h > 0) && !isCreate && original && original.images && original.images[0] && original.images[0].src === src) {
      w = original.images[0].w || 0;
      h = original.images[0].h || 0;
    }
    if (draft.imageWidth > 0 && draft.imageHeight > 0) {
      w = draft.imageWidth;
      h = draft.imageHeight;
    }

    var unit = unitMeta(draft.unit);
    var cut = trim(draft.cut);
    if (!cut && !isCreate && original && original.category === category) {
      cut = original.cut || "";
    }

    var payload = {
      id: id,
      name: name,
      category: category,
      group: groupForCategory(category) || (original && original.group) || "",
      condition: condition,
      cut: cut,
      priceBasis: unit.priceBasis,
      priceUnit: unit.priceUnit,
      status: availability,
      badge: condition,
      defaultVariant: unit.variantId,
      desc: trim(draft.desc),
      images: [{ src: src, alt: trim(draft.imageAlt), w: w, h: h }],
      variants: [{
        id: unit.variantId,
        label: unit.variantLabel,
        price: price.ok ? price.value : 0
      }]
    };
    return payload;
  }

  /* ==========================================================================
     Persistence boundary
     ========================================================================== */
  var ProductStore = {
    savePayload: function (payload) {
      var saved = false;
      try {
        if (window.FreshDirectAdminStore && window.FreshDirectAdminStore.upsert) {
          saved = !!window.FreshDirectAdminStore.upsert(payload);
        }
      } catch (e) {
        saved = false;
      }
      return Promise.resolve({ saved: saved, payload: payload });
    }
  };

  /* ==========================================================================
     UI controller
     ========================================================================== */
  function readMode() {
    var params = null;
    try {
      params = new URLSearchParams(window.location.search);
    } catch (e) {
      params = null;
    }
    var scenario = "normal";
    var id = "";
    var deliberateNew = false;
    if (params) {
      var mock = params.get("mock") || "normal";
      if (mock === "error") {
        scenario = "error";
      }
      id = trim(params.get("id") || "");
      deliberateNew = (params.get("mode") || "").toLowerCase() === "new";
    }
    if (deliberateNew || !id) {
      return { mode: "create", id: "", scenario: scenario };
    }
    return { mode: "edit", id: id, scenario: scenario };
  }

  function setFieldError(input, errorEl, message) {
    if (!input || !errorEl) {
      return;
    }
    if (message) {
      errorEl.textContent = message;
      errorEl.removeAttribute("hidden");
      input.setAttribute("aria-invalid", "true");
    } else {
      errorEl.textContent = "";
      errorEl.setAttribute("hidden", "");
      input.removeAttribute("aria-invalid");
    }
  }

  function init() {
    if (!el("fd-ed-form")) {
      return;
    }
    var mode = readMode();

    var loadingBox = el("fd-ed-loading");
    var errorBox = el("fd-ed-error");
    var missingBox = el("fd-ed-missing");
    var content = el("fd-ed-content");
    var form = el("fd-ed-form");
    var heading = el("fd-ed-heading");
    var lead = el("fd-ed-lead");
    var topbarTitle = el("fd-ed-topbar-title");
    var submitLabel = el("fd-ed-submit-label");
    var submitBtn = el("fd-ed-submit");
    var identitySection = el("fd-ed-identity-section");
    var identityId = el("fd-ed-product-id");
    var summary = el("fd-ed-summary");
    var summaryTitle = el("fd-ed-summary-title");
    var summaryList = el("fd-ed-summary-list");
    var resultBox = el("fd-ed-result");
    var resultTitle = el("fd-ed-result-title");
    var resultNote = el("fd-ed-result-note");
    var resultNew = el("fd-ed-result-new");
    var cancelLink = el("fd-ed-cancel");

    var nameInput = el("fd-ed-name");
    var categorySelect = el("fd-ed-category");
    var unitSelect = el("fd-ed-unit");
    var conditionSelect = el("fd-ed-condition");
    var conditionHint = el("fd-ed-condition-hint");
    var availabilitySelect = el("fd-ed-availability");
    var descInput = el("fd-ed-desc");
    var cutInput = el("fd-ed-cut");
    var priceLabel = el("fd-ed-price-label");
    var priceSuffix = el("fd-ed-price-suffix");
    var priceHint = el("fd-ed-price-hint");
    var imageSrcInput = el("fd-ed-image-src");
    var imageAltInput = el("fd-ed-image-alt");
    var imageOptions = el("fd-ed-image-options");
    var imagePick = el("fd-ed-image-pick");
    var imageFileInput = el("fd-ed-image-file");
    var imageFileError = el("fd-ed-image-file-error");
    var imageStatus = el("fd-ed-image-status");
    var imageFileInfo = el("fd-ed-image-fileinfo");
    var imageRemoveBtn = el("fd-ed-image-remove");
    var previewImg = el("fd-ed-preview-img");
    var previewCap = el("fd-ed-preview-cap");
    var priceInput = el("fd-ed-price");

    var catalog = null;
    var knownImages = [];
    var original = null;
    var isCreate = mode.mode === "create";
    var populating = true;
    var dirty = false;
    var submitted = false;
    var submitting = false;
    var pendingUpload = null;
    var uploadBusy = false;

    function showOnly(state) {
      if (loadingBox) {
        loadingBox.hidden = state !== "loading";
      }
      if (errorBox) {
        errorBox.hidden = state !== "error";
      }
      if (missingBox) {
        missingBox.hidden = state !== "missing";
      }
      if (content) {
        content.hidden = state !== "ready";
      }
    }

    function markDirty() {
      if (!populating && !submitted) {
        dirty = true;
      }
    }

    function applyModeText(entry) {
      if (isCreate) {
        document.title = "Add Product | O’TOOSIN Farms Admin";
        if (heading) {
          heading.textContent = "Add Product";
        }
        if (topbarTitle) {
          topbarTitle.textContent = "Add Product";
        }
        if (lead) {
          lead.textContent = "Add a product with its category, selling unit, condition, price and photo.";
        }
        if (submitLabel) {
          submitLabel.textContent = "Add Product";
        }
        if (identitySection) {
          identitySection.hidden = true;
        }
      } else {
        document.title = "Edit " + entry.name + " | O’TOOSIN Farms Admin";
        if (heading) {
          heading.textContent = "Edit Product";
        }
        if (topbarTitle) {
          topbarTitle.textContent = "Edit Product";
        }
        if (lead) {
          lead.textContent = "Update “" + entry.name + "” and keep the same product ID.";
        }
        if (submitLabel) {
          submitLabel.textContent = "Save Changes";
        }
        if (identitySection) {
          identitySection.hidden = false;
        }
        if (identityId) {
          identityId.textContent = entry.id;
        }
      }
    }

    function populateImageOptions() {
      if (imageOptions) {
        imageOptions.innerHTML = "";
      }
      if (imagePick) {
        imagePick.innerHTML = "";
        var placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Choose an image…";
        imagePick.appendChild(placeholder);
      }
      for (var i = 0; i < knownImages.length; i++) {
        if (imageOptions) {
          var option = document.createElement("option");
          option.value = knownImages[i].src;
          option.label = knownImages[i].alt || knownImages[i].src;
          imageOptions.appendChild(option);
        }
        if (imagePick) {
          var choice = document.createElement("option");
          choice.value = knownImages[i].src;
          choice.textContent = knownImages[i].alt || knownImages[i].src;
          choice.setAttribute("data-alt", knownImages[i].alt || "");
          imagePick.appendChild(choice);
        }
      }
      syncImagePick();
    }

    function syncImagePick() {
      if (!imagePick || !imageSrcInput) {
        return;
      }
      var current = trim(imageSrcInput.value);
      var found = false;
      for (var i = 0; i < imagePick.options.length; i++) {
        if (imagePick.options[i].value && imagePick.options[i].value === current) {
          found = true;
        }
      }
      imagePick.value = found ? current : "";
    }

    function populateConditions(selected) {
      if (!conditionSelect) {
        return;
      }
      var category = categorySelect ? categorySelect.value : "";
      var allowed = category ? conditionsForCategory(category) : [];
      conditionSelect.innerHTML = "";
      var placeholder = document.createElement("option");
      placeholder.value = "";
      if (!category) {
        placeholder.textContent = "Choose a category first";
        conditionSelect.appendChild(placeholder);
        conditionSelect.disabled = true;
        return;
      }
      placeholder.textContent = "Choose a condition…";
      conditionSelect.appendChild(placeholder);
      for (var i = 0; i < allowed.length; i++) {
        var option = document.createElement("option");
        option.value = allowed[i];
        option.textContent = allowed[i];
        conditionSelect.appendChild(option);
      }
      conditionSelect.disabled = false;
      conditionSelect.value = allowed.indexOf(selected) !== -1
        ? selected
        : allowed[0];
      if (conditionHint) {
        conditionHint.textContent = categoryGroup(category) === "Meats" ||
          category === "Fish"
          ? "Fresh and Frozen describe how it is kept; Fried marks ready-to-eat products."
          : category === "Live Animals"
            ? "Live products are collected or delivered alive."
            : "Fresh is the current state for this farm category.";
      }
    }

    function updateUnitText() {
      var meta = unitMeta(unitSelect ? unitSelect.value : "kg");
      if (priceLabel) {
        priceLabel.textContent = meta.priceLabel;
      }
      if (priceSuffix) {
        priceSuffix.textContent = meta.suffix;
      }
      if (priceHint) {
        priceHint.textContent = meta.priceHint;
      }
    }

    function syncCategoryFields() {
      var category = categorySelect ? categorySelect.value : "";
      var currentCondition = conditionSelect ? conditionSelect.value : "";
      populateConditions(currentCondition);
      if (isCreate && unitSelect) {
        unitSelect.value = defaultUnitForCategory(category);
      }
      updateUnitText();
    }

    function hideSummary() {
      if (summary) {
        summary.hidden = true;
      }
    }

    function clearAllErrors() {
      hideSummary();
      setFieldError(nameInput, el("fd-ed-name-error"), "");
      setFieldError(categorySelect, el("fd-ed-category-error"), "");
      setFieldError(unitSelect, el("fd-ed-unit-error"), "");
      setFieldError(conditionSelect, el("fd-ed-condition-error"), "");
      setFieldError(availabilitySelect, el("fd-ed-availability-error"), "");
      setFieldError(descInput, el("fd-ed-desc-error"), "");
      setFieldError(cutInput, el("fd-ed-cut-error"), "");
      setFieldError(imageSrcInput, el("fd-ed-image-src-error"), "");
      setFieldError(imageFileInput, imageFileError, "");
      setFieldError(imageAltInput, el("fd-ed-image-alt-error"), "");
      setFieldError(priceInput, el("fd-ed-price-error"), "");
    }

    function showErrors(errors) {
      clearAllErrors();
      if (!errors.length) {
        return;
      }
      summaryList.innerHTML = "";
      for (var i = 0; i < errors.length; i++) {
        var err = errors[i];
        var item = document.createElement("li");
        var link = document.createElement("a");
        link.setAttribute("href", "#" + err.target);
        link.textContent = err.message;
        item.appendChild(link);
        summaryList.appendChild(item);

        if (err.target === "fd-ed-image-file") {
          setFieldError(imageFileInput, imageFileError, err.message);
        } else {
          var input = document.getElementById(err.target);
          var errorEl = document.getElementById(err.target + "-error");
          setFieldError(input, errorEl, err.message);
        }
      }
      if (summaryTitle) {
        summaryTitle.textContent = "Check the highlighted fields.";
      }
      summary.hidden = false;
      summary.focus();
      summary.scrollIntoView({ block: "start" });
    }

    /* ----- Image preview ----- */
    var previewTimer = null;
    function syncPreview() {
      var alt = trim(imageAltInput.value);
      var src = trim(imageSrcInput.value);
      if (!src) {
        window.clearTimeout(previewTimer);
        previewImg.hidden = true;
        previewImg.removeAttribute("src");
        previewCap.textContent = "Image preview appears here.";
        return;
      }
      previewCap.textContent = "Loading preview…";
      window.clearTimeout(previewTimer);
      previewTimer = window.setTimeout(function () {
        previewImg.onload = function () {
          previewImg.hidden = false;
          previewCap.textContent = alt || "Preview loaded.";
        };
        previewImg.onerror = function () {
          previewImg.hidden = true;
          previewImg.removeAttribute("src");
          previewCap.textContent = "Preview could not be loaded. Choose another image.";
        };
        previewImg.setAttribute("alt", alt || "Product image preview");
        previewImg.setAttribute("src", src);
      }, 180);
    }

    function updateUploadStatus() {
      if (!imageStatus) {
        return;
      }
      if (pendingUpload) {
        var bits = "Selected “" + pendingUpload.name + "” (" +
          formatFileSize(pendingUpload.size) + ")";
        if (pendingUpload.width > 0 && pendingUpload.height > 0) {
          bits += " · " + pendingUpload.width + " × " + pendingUpload.height + " px";
        }
        bits += " — ready to save with this product.";
        imageStatus.textContent = bits;
        if (imageFileInfo) {
          imageFileInfo.textContent = pendingUpload.name + " · " +
            formatFileSize(pendingUpload.size);
          imageFileInfo.hidden = false;
        }
      } else {
        var current = trim(imageSrcInput.value);
        imageStatus.textContent = current
          ? "Using the selected product image."
          : "No image selected yet.";
        if (imageFileInfo) {
          imageFileInfo.textContent = "";
          imageFileInfo.hidden = true;
        }
      }
      if (imageRemoveBtn) {
        imageRemoveBtn.hidden = !trim(imageSrcInput.value);
      }
    }

    function handleImageFile() {
      if (!imageFileInput || !imageFileInput.files || !imageFileInput.files.length) {
        return;
      }
      if (uploadBusy) {
        return;
      }
      var file = imageFileInput.files[0];
      var checked = validateImageFile(file);
      if (!checked.ok) {
        setFieldError(imageFileInput, imageFileError,
          imageFileErrorText(checked.error, file.name));
        try {
          imageFileInput.value = "";
        } catch (e) {
          /* Resetting the picker is best-effort. */
        }
        updateUploadStatus();
        return;
      }
      uploadBusy = true;
      setFieldError(imageFileInput, imageFileError, "");
      if (imageStatus) {
        imageStatus.textContent = "Preparing “" + file.name + "”…";
      }
      prepareImageFile(file).then(function (prepared) {
        pendingUpload = {
          name: file.name,
          size: file.size,
          width: prepared.width,
          height: prepared.height,
          src: prepared.src
        };
        imageSrcInput.value = prepared.src;
        setFieldError(imageSrcInput, el("fd-ed-image-src-error"), "");
        if (!trim(imageAltInput.value)) {
          imageAltInput.value = altFromFilename(file.name);
          setFieldError(imageAltInput, el("fd-ed-image-alt-error"), "");
        }
        hideSummary();
        markDirty();
        syncImagePick();
        updateUploadStatus();
        syncPreview();
      }, function () {
        setFieldError(imageFileInput, imageFileError,
          imageFileErrorText("unreadable", file.name));
        try {
          imageFileInput.value = "";
        } catch (e) {
          /* Resetting the picker is best-effort. */
        }
        updateUploadStatus();
      }).then(function () {
        uploadBusy = false;
      });
    }

    function removeImage() {
      pendingUpload = null;
      imageSrcInput.value = "";
      setFieldError(imageSrcInput, el("fd-ed-image-src-error"), "");
      setFieldError(imageFileInput, imageFileError, "");
      if (imageFileInput) {
        try {
          imageFileInput.value = "";
        } catch (e) {
          /* Resetting the picker is best-effort. */
        }
      }
      hideSummary();
      markDirty();
      updateUploadStatus();
      syncPreview();
    }

    function readDraft() {
      return {
        name: nameInput.value,
        category: categorySelect.value,
        unit: unitSelect ? unitSelect.value : "kg",
        condition: conditionSelect.value,
        availability: availabilitySelect ? availabilitySelect.value : "",
        desc: descInput.value,
        cut: cutInput ? cutInput.value : "",
        imageSrc: imageSrcInput.value,
        imageAlt: imageAltInput.value,
        imageWidth: pendingUpload ? pendingUpload.width : 0,
        imageHeight: pendingUpload ? pendingUpload.height : 0,
        price: priceInput.value
      };
    }

    function setSubmitting(on) {
      submitting = on;
      if (submitBtn) {
        submitBtn.disabled = on;
        if (on) {
          submitBtn.setAttribute("aria-busy", "true");
        } else {
          submitBtn.removeAttribute("aria-busy");
        }
      }
      if (submitLabel) {
        submitLabel.textContent = on
          ? "Saving…"
          : (isCreate ? "Add Product" : "Save Changes");
      }
    }

    function showSubmitFailure(message) {
      summaryList.innerHTML = "";
      var item = document.createElement("li");
      item.textContent = message;
      summaryList.appendChild(item);
      if (summaryTitle) {
        summaryTitle.textContent = "The product could not be saved.";
      }
      summary.hidden = false;
      summary.focus();
      summary.scrollIntoView({ block: "start" });
    }

    function onSubmit(ev) {
      ev.preventDefault();
      if (submitting || submitted) {
        return;
      }
      if (resultBox && !resultBox.hidden) {
        resultBox.hidden = true;
      }
      var draft = readDraft();
      var errors = validateProduct(draft, { categories: CATEGORIES });
      if (errors.length) {
        showErrors(errors);
        var first = errors[0] && document.getElementById(errors[0].target);
        if (first && first.focus) {
          try {
            first.focus({ preventScroll: true });
          } catch (e) {
            first.focus();
          }
        }
        return;
      }
      clearAllErrors();
      var payload = buildPayload(draft, {
        isCreate: isCreate,
        catalog: catalog,
        original: original,
        knownImages: knownImages
      });
      setSubmitting(true);
      ProductStore.savePayload(payload).then(function (result) {
        setSubmitting(false);
        if (!result.saved) {
          showSubmitFailure("We could not save this product. Check your entries and try again.");
          return;
        }
        submitted = true;
        dirty = false;
        showResult(result.payload);
      }, function () {
        setSubmitting(false);
        showSubmitFailure("We could not save this product. Check your entries and try again.");
      });
    }

    function showResult(payload) {
      if (resultTitle) {
        resultTitle.textContent = isCreate ? "Product created" : "Changes saved";
      }
      resultNote.innerHTML = "";
      var strong = document.createElement("strong");
      strong.textContent = isCreate ? "Product created." : "Changes saved.";
      resultNote.appendChild(strong);
      resultNote.appendChild(document.createTextNode(
        isCreate
          ? " “" + payload.name + "” is now in your product records."
          : " “" + payload.name + "” has been updated."
      ));
      renderResultSummary(payload);
      if (resultNew) {
        resultNew.hidden = !isCreate;
      }
      form.hidden = true;
      resultBox.hidden = false;
      resultTitle.focus();
      resultBox.scrollIntoView({ block: "start" });
    }

    function renderResultSummary(payload) {
      var host = el("fd-ed-result-summary");
      if (!host) {
        return;
      }
      host.innerHTML = "";
      var card = document.createElement("div");
      card.className = "fd-edit-result-card";

      var image = (payload.images && payload.images[0]) || { src: "", alt: "" };
      if (image.src) {
        var thumb = document.createElement("span");
        thumb.className = "fd-edit-result-thumb";
        thumb.setAttribute("aria-hidden", "true");
        var thumbImg = document.createElement("img");
        thumbImg.setAttribute("src", image.src);
        thumbImg.setAttribute("alt", "");
        thumbImg.setAttribute("loading", "lazy");
        thumbImg.setAttribute("decoding", "async");
        thumbImg.onerror = function () {
          thumbImg.style.display = "none";
        };
        thumb.appendChild(thumbImg);
        card.appendChild(thumb);
      }

      var body = document.createElement("div");
      body.className = "fd-edit-result-body";

      var name = document.createElement("strong");
      name.className = "fd-edit-result-name";
      name.textContent = payload.name;
      body.appendChild(name);

      var meta = document.createElement("span");
      meta.className = "fd-edit-result-meta";
      meta.textContent = payload.category + " · " + payload.condition + " · " +
        availabilityLabel(payload.status);
      body.appendChild(meta);

      var price = document.createElement("span");
      price.className = "fd-edit-result-price";
      var unitPrice = payload.variants && payload.variants[0] ? payload.variants[0].price : 0;
      price.textContent = fmtNaira(unitPrice) + " " + unitMeta(resolveUnitKey(payload)).suffix;
      body.appendChild(price);

      if (payload.desc) {
        var desc = document.createElement("p");
        desc.className = "fd-edit-result-desc";
        desc.textContent = payload.desc;
        body.appendChild(desc);
      }
      card.appendChild(body);
      host.appendChild(card);
    }

    function boot() {
      showOnly("loading");
      populating = true;
      var data;
      try {
        if (mode.scenario === "error") {
          throw new Error("Product details could not be loaded.");
        }
        data = getCatalog();
      } catch (e) {
        populating = false;
        showOnly("error");
        return;
      }
      catalog = data;
      knownImages = listKnownImages(catalog);

      if (!isCreate) {
        original = catalog[mode.id] || null;
        if (!original) {
          populating = false;
          var missingText = el("fd-ed-missing-text");
          if (missingText) {
            missingText.textContent = "No product with ID “" + mode.id + "” exists. Check the Products list for the correct item.";
          }
          showOnly("missing");
          document.title = "Product not found | O’TOOSIN Farms Admin";
          if (heading) {
            heading.textContent = "Product not found";
          }
          if (topbarTitle) {
            topbarTitle.textContent = "Product not found";
          }
          if (lead) {
            lead.textContent = "The requested product is not in the catalogue.";
          }
          return;
        }
      }

      applyModeText(original || { name: "" });
      populateImageOptions();

      if (isCreate) {
        nameInput.value = "";
        categorySelect.value = "";
        unitSelect.value = "";
        conditionSelect.value = "";
        availabilitySelect.value = "in";
        descInput.value = "";
        cutInput.value = "";
        imageSrcInput.value = "";
        imageAltInput.value = "";
        priceInput.value = "";
        populateConditions("");
      } else {
        nameInput.value = original.name || "";
        categorySelect.value = original.category || "";
        unitSelect.value = resolveUnitKey(original);
        availabilitySelect.value = AVAILABILITY.indexOf(original.status) !== -1
          ? original.status
          : "in";
        descInput.value = original.desc || "";
        cutInput.value = original.cut || "";
        populateConditions(original.condition || "");
        var firstImage = (original.images && original.images[0]) || { src: "", alt: "" };
        imageSrcInput.value = firstImage.src || "";
        imageAltInput.value = firstImage.alt || "";
        var variant = (original.variants && original.variants[0]) || null;
        if (!variant && original.defaultVariant && original.variants) {
          for (var i = 0; i < original.variants.length; i++) {
            if (original.variants[i].id === original.defaultVariant) {
              variant = original.variants[i];
            }
          }
        }
        priceInput.value = variant && variant.price != null ? String(variant.price) : "";
      }
      updateUnitText();

      pendingUpload = null;
      if (imageFileInput) {
        try {
          imageFileInput.value = "";
        } catch (e) {
          /* Resetting the picker is best-effort. */
        }
      }
      populating = false;
      showOnly("ready");
      syncImagePick();
      syncPreview();
      updateUploadStatus();
    }

    /* ----- Wiring ----- */
    form.addEventListener("submit", onSubmit);

    var tracked = [nameInput, categorySelect, unitSelect, conditionSelect, availabilitySelect, descInput, cutInput, priceInput, imageAltInput];
    for (var t = 0; t < tracked.length; t++) {
      (function (input) {
        if (!input) {
          return;
        }
        var eventName = input.tagName === "SELECT" ? "change" : "input";
        input.addEventListener(eventName, function () {
          var map = {
            "fd-ed-name": "fd-ed-name-error",
            "fd-ed-category": "fd-ed-category-error",
            "fd-ed-unit": "fd-ed-unit-error",
            "fd-ed-condition": "fd-ed-condition-error",
            "fd-ed-availability": "fd-ed-availability-error",
            "fd-ed-desc": "fd-ed-desc-error",
            "fd-ed-cut": "fd-ed-cut-error",
            "fd-ed-price": "fd-ed-price-error",
            "fd-ed-image-alt": "fd-ed-image-alt-error"
          };
          setFieldError(input, el(map[input.id]), "");
          hideSummary();
          markDirty();
          if (input === imageAltInput) {
            syncPreview();
          }
        });
      })(tracked[t]);
    }

    if (categorySelect) {
      categorySelect.addEventListener("change", function () {
        syncCategoryFields();
      });
    }

    if (unitSelect) {
      unitSelect.addEventListener("change", function () {
        updateUnitText();
      });
    }

    if (imageSrcInput) {
      imageSrcInput.addEventListener("input", function () {
        setFieldError(imageSrcInput, el("fd-ed-image-src-error"), "");
        hideSummary();
        markDirty();
        syncImagePick();
        syncPreview();
      });
    }

    if (imagePick) {
      imagePick.addEventListener("change", function () {
        if (!imagePick.value) {
          return;
        }
        pendingUpload = null;
        if (imageFileInput) {
          try {
            imageFileInput.value = "";
          } catch (e) {
            /* Resetting the picker is best-effort. */
          }
        }
        imageSrcInput.value = imagePick.value;
        setFieldError(imageSrcInput, el("fd-ed-image-src-error"), "");
        setFieldError(imageFileInput, imageFileError, "");
        hideSummary();
        markDirty();
        if (!trim(imageAltInput.value)) {
          var selected = imagePick.options[imagePick.selectedIndex];
          imageAltInput.value = selected ? (selected.getAttribute("data-alt") || "") : "";
          setFieldError(imageAltInput, el("fd-ed-image-alt-error"), "");
        }
        updateUploadStatus();
        syncPreview();
      });
    }

    if (imageFileInput) {
      imageFileInput.addEventListener("change", handleImageFile);
    }

    if (imageRemoveBtn) {
      imageRemoveBtn.addEventListener("click", removeImage);
    }

    var retryBtn = el("fd-ed-retry");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        window.location.reload();
      });
    }

    if (cancelLink) {
      cancelLink.addEventListener("click", function (ev) {
        if (dirty && !submitted) {
          var leave = window.confirm("Leave without saving? Your changes will be lost.");
          if (!leave) {
            ev.preventDefault();
          }
        }
      });
    }

    window.addEventListener("beforeunload", function (ev) {
      if (dirty && !submitted) {
        ev.preventDefault();
        ev.returnValue = "";
      }
    });

    boot();
  }

  if (typeof window !== "undefined") {
    window.FreshDirectAdminProductEditor = {
      readMode: readMode,
      listKnownImages: listKnownImages,
      productIdFromName: productIdFromName,
      parsePrice: parsePrice,
      validate: validateProduct,
      buildPayload: buildPayload,
      categories: CATEGORIES.slice(),
      categoryGroups: CATEGORY_GROUP,
      conditions: ALL_CONDITIONS.slice(),
      conditionsForCategory: conditionsForCategory,
      units: Object.keys(UNITS),
      availability: AVAILABILITY.slice(),
      availabilityLabels: {
        "in": AVAILABILITY_LABELS.in,
        "limited": AVAILABILITY_LABELS.limited,
        "out": AVAILABILITY_LABELS.out
      },
      maxPrice: MAX_PRICE
    };
    window.FreshDirectAdminProductStore = ProductStore;
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
})();
