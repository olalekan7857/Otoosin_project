/* ==========================================================================
   O’TOOSIN Farms Admin — Settings page controller
   --------------------------------------------------------------------------
   One form owns all editable settings. The data boundary
   (window.FreshDirectAdminSettings in fd-admin-settings-data.js) is the only
   source of settings values and the only place a save is attempted. The
   page never fabricates success: it renders the record returned after a
   verified save, or the service's field/form errors.
   ========================================================================== */
(function () {
  "use strict";

  var FIELDS = [
    { key: "businessName", input: "fd-settings-name", label: "Business name" },
    { key: "address", input: "fd-settings-address", label: "Business address" },
    { key: "whatsapp", input: "fd-settings-whatsapp", label: "WhatsApp number" },
    { key: "contactPhone", input: "fd-settings-phone", label: "Contact phone number" },
    { key: "description", input: "fd-settings-description", label: "Storefront introduction" }
  ];

  var snapshot = null;
  var busy = false;
  var navWired = false;
  var scrollQueued = false;
  var editingLocationId = "";

  function svc() {
    return window.FreshDirectAdminSettings || null;
  }

  function byId(id) {
    return document.getElementById(id);
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

  function fieldByKey(key) {
    for (var i = 0; i < FIELDS.length; i++) {
      if (FIELDS[i].key === key) {
        return FIELDS[i];
      }
    }
    return null;
  }

  function fieldByInput(id) {
    for (var i = 0; i < FIELDS.length; i++) {
      if (FIELDS[i].input === id) {
        return FIELDS[i];
      }
    }
    return null;
  }

  /* ---------- Page states ---------- */
  function showLoading() {
    var loading = byId("fd-settings-loading");
    var content = byId("fd-settings-content");
    var error = byId("fd-settings-error");
    if (loading) {
      loading.removeAttribute("hidden");
    }
    if (content) {
      content.setAttribute("hidden", "");
      content.setAttribute("aria-busy", "true");
    }
    if (error) {
      error.setAttribute("hidden", "");
    }
  }

  function showContent() {
    var loading = byId("fd-settings-loading");
    var content = byId("fd-settings-content");
    var error = byId("fd-settings-error");
    if (loading) {
      loading.setAttribute("hidden", "");
    }
    if (error) {
      error.setAttribute("hidden", "");
    }
    if (content) {
      content.removeAttribute("hidden");
      content.setAttribute("aria-busy", "false");
    }
  }

  function showError() {
    var loading = byId("fd-settings-loading");
    var content = byId("fd-settings-content");
    var error = byId("fd-settings-error");
    if (loading) {
      loading.setAttribute("hidden", "");
    }
    if (content) {
      content.setAttribute("hidden", "");
      content.setAttribute("aria-busy", "false");
    }
    if (error) {
      error.removeAttribute("hidden");
      var retry = byId("fd-settings-retry");
      if (retry) {
        retry.focus();
      }
    }
  }

  /* ---------- Field errors ---------- */
  function setFieldError(field, message) {
    if (!field) {
      return;
    }
    var input = byId(field.input);
    var error = byId(field.input + "-error");
    if (!input) {
      return;
    }
    if (message) {
      input.setAttribute("aria-invalid", "true");
      if (error) {
        error.textContent = message;
        error.removeAttribute("hidden");
        var described = input.getAttribute("aria-describedby") || "";
        if (described.indexOf(error.id) === -1) {
          input.setAttribute("aria-describedby", described ? described + " " + error.id : error.id);
        }
      }
    } else {
      input.removeAttribute("aria-invalid");
      if (error) {
        error.textContent = "";
        error.setAttribute("hidden", "");
        var parts = (input.getAttribute("aria-describedby") || "").split(/\s+/);
        var kept = [];
        for (var i = 0; i < parts.length; i++) {
          if (parts[i] && parts[i] !== error.id) {
            kept.push(parts[i]);
          }
        }
        if (kept.length) {
          input.setAttribute("aria-describedby", kept.join(" "));
        } else {
          input.removeAttribute("aria-describedby");
        }
      }
    }
  }

  function clearErrors() {
    for (var i = 0; i < FIELDS.length; i++) {
      setFieldError(FIELDS[i], "");
    }
  }

  /* ---------- Form alert and feedback ---------- */
  function hideAlert() {
    var alert = byId("fd-settings-alert");
    var list = byId("fd-settings-alert-list");
    if (alert) {
      alert.setAttribute("hidden", "");
    }
    if (list) {
      list.innerHTML = "";
    }
  }

  function showAlert(title, messages) {
    var alert = byId("fd-settings-alert");
    var titleEl = byId("fd-settings-alert-title");
    var list = byId("fd-settings-alert-list");
    if (!alert || !list) {
      return;
    }
    list.innerHTML = "";
    for (var i = 0; i < messages.length; i++) {
      var item = document.createElement("li");
      item.textContent = messages[i];
      list.appendChild(item);
    }
    if (titleEl && title) {
      titleEl.textContent = title;
    }
    alert.removeAttribute("hidden");
    try {
      alert.focus();
    } catch (e) {
      /* focus is best-effort */
    }
  }

  function setFeedback(message, isError, focus) {
    var note = byId("fd-settings-feedback");
    if (!note) {
      return;
    }
    if (!message) {
      note.textContent = "";
      note.setAttribute("hidden", "");
      note.classList.remove("is-error");
      return;
    }
    note.textContent = message;
    note.classList.toggle("is-error", !!isError);
    note.removeAttribute("hidden");
    if (focus) {
      try {
        note.focus();
      } catch (e) {
        /* focus is best-effort */
      }
    }
  }

  /* ---------- Form values ---------- */
  function readForm() {
    var values = {};
    for (var i = 0; i < FIELDS.length; i++) {
      var input = byId(FIELDS[i].input);
      values[FIELDS[i].key] = input ? input.value : "";
    }
    return values;
  }

  function isDirty() {
    if (!snapshot) {
      return false;
    }
    var current = readForm();
    for (var i = 0; i < FIELDS.length; i++) {
      var key = FIELDS[i].key;
      if ((current[key] || "") !== (snapshot[key] || "")) {
        return true;
      }
    }
    return false;
  }

  function paintDirty() {
    var dirty = isDirty();
    var submit = byId("fd-settings-submit");
    var discard = byId("fd-settings-discard");
    var hint = byId("fd-settings-dirty");
    if (submit) {
      submit.disabled = busy || !dirty;
    }
    if (discard) {
      discard.disabled = busy || !dirty;
    }
    if (hint) {
      if (dirty) {
        hint.removeAttribute("hidden");
      } else {
        hint.setAttribute("hidden", "");
      }
    }
  }

  function paintDescription() {
    var input = byId("fd-settings-description");
    var count = byId("fd-settings-description-count");
    var preview = byId("fd-settings-description-preview");
    if (!input) {
      return;
    }
    if (count) {
      count.textContent = input.value.length + " / 500";
    }
    if (preview) {
      var text = input.value.trim();
      preview.textContent = text || "Your introduction will appear here.";
    }
  }

  function setBusy(on) {
    busy = !!on;
    var submit = byId("fd-settings-submit");
    var label = byId("fd-settings-submit-label");
    var discard = byId("fd-settings-discard");
    if (submit) {
      submit.setAttribute("aria-busy", busy ? "true" : "false");
    }
    if (label) {
      label.textContent = busy ? "Saving…" : "Save changes";
    }
    if (discard) {
      discard.disabled = busy || !isDirty();
    }
    for (var i = 0; i < FIELDS.length; i++) {
      var input = byId(FIELDS[i].input);
      if (input) {
        input.disabled = busy;
      }
    }
    paintDirty();
  }

  function fill(settings) {
    var values = settings || {};
    for (var i = 0; i < FIELDS.length; i++) {
      var input = byId(FIELDS[i].input);
      if (input) {
        input.value = values[FIELDS[i].key] != null ? values[FIELDS[i].key] : "";
      }
    }
    snapshot = readForm();
    clearErrors();
    hideAlert();
    setFeedback("", false, false);
    paintDescription();
    paintDirty();
  }

  /* ---------- Read-only brand, delivery and category records ---------- */
  function setText(id, value) {
    var node = byId(id);
    if (node) {
      node.textContent = value || "—";
    }
  }

  function fmtNaira(value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    var amount = Number(value);
    if (!isFinite(amount)) {
      return "—";
    }
    return "₦" + amount.toLocaleString("en-NG");
  }

  function emptyNote(text) {
    var item = document.createElement("li");
    item.className = "fd-settings-list-empty";
    item.textContent = text;
    return item;
  }

  function renderBrand() {
    var s = svc();
    if (!s || typeof s.getBrandInfo !== "function") {
      return;
    }
    var info;
    try {
      info = s.getBrandInfo();
    } catch (e) {
      return;
    }
    if (!info) {
      return;
    }
    setText("fd-settings-slogan", info.slogan);
    var logo = info.logo || {};
    var image = byId("fd-settings-logo-img");
    if (image && logo.src) {
      image.src = logo.src;
      image.alt = logo.alt || "O’TOOSIN Farms";
    }
    setText("fd-settings-logo-path", logo.reference || logo.src || "—");
  }

  function renderZones(zones) {
    var list = byId("fd-settings-zone-list");
    if (!list) {
      return;
    }
    list.innerHTML = "";
    if (!zones || !zones.length) {
      list.appendChild(emptyNote("No doorstep zones are configured."));
      return;
    }
    for (var i = 0; i < zones.length; i++) {
      var zone = zones[i] || {};
      var item = document.createElement("li");
      item.className = "fd-settings-zone";
      var text = document.createElement("div");
      text.className = "fd-settings-zone-text";
      var name = document.createElement("strong");
      name.className = "fd-settings-zone-name";
      name.textContent = zone.name || "Delivery zone";
      var areas = document.createElement("span");
      areas.className = "fd-settings-zone-areas";
      areas.textContent =
        (zone.areas || "Area details not set.") +
        (zone.active === false ? " (inactive)" : "");
      var fee = document.createElement("span");
      fee.className = "fd-settings-zone-fee";
      fee.textContent = fmtNaira(zone.fee);
      text.appendChild(name);
      text.appendChild(areas);
      item.appendChild(text);
      item.appendChild(fee);
      list.appendChild(item);
    }
  }

  function renderPickupLocations(locations) {
    var list = byId("fd-settings-pickup-list");
    if (!list) {
      return;
    }
    list.innerHTML = "";
    if (!locations || !locations.length) {
      list.appendChild(emptyNote("No pickup locations are configured."));
      return;
    }
    for (var i = 0; i < locations.length; i++) {
      var location = locations[i] || {};
      var item = document.createElement("li");
      item.className = "fd-settings-pickup";
      var name = document.createElement("strong");
      name.className = "fd-settings-pickup-name";
      name.textContent = location.name || "Pickup location";
      var address = document.createElement("span");
      address.className = "fd-settings-pickup-address";
      address.textContent = location.address || "Address not set.";
      var fee = document.createElement("span");
      fee.className = "fd-dash-pill is-ok";
      fee.textContent = "No delivery fee";
      item.appendChild(name);
      item.appendChild(address);
      item.appendChild(fee);
      list.appendChild(item);
    }
  }

  function renderParkDestinations(destinations) {
    var list = byId("fd-settings-park-list");
    if (!list) {
      return;
    }
    list.innerHTML = "";
    if (!destinations || !destinations.length) {
      list.appendChild(emptyNote("No park destinations are configured."));
      return;
    }
    for (var i = 0; i < destinations.length; i++) {
      var destination = destinations[i];
      var item = document.createElement("li");
      if (destination && typeof destination === "object") {
        item.textContent =
          destination.name +
          " — " + fmtNaira(destination.fee) +
          (destination.active === false ? " (inactive)" : "");
      } else {
        item.textContent = destination;
      }
      list.appendChild(item);
    }
  }

  function renderDelivery() {
    var s = svc();
    if (!s || typeof s.getDeliveryInfo !== "function") {
      return;
    }
    var info;
    try {
      info = s.getDeliveryInfo();
    } catch (e) {
      return;
    }
    if (!info) {
      return;
    }
    setText("fd-settings-delivery-coverage", info.coverage);
    setText("fd-settings-doorstep-note", info.doorstep);
    setText("fd-settings-park-note", info.park);
    setText("fd-settings-pickup-note", info.pickup);
    setText("fd-settings-delivery-payment", info.payment);
    renderZones(info.zones);
    renderPickupLocations(info.pickupLocations);
    renderParkDestinations(info.parkDestinations);
  }

  function renderCategories() {
    var s = svc();
    if (!s || typeof s.getMarketplaceCategories !== "function") {
      return;
    }
    var list = byId("fd-settings-category-list");
    if (!list) {
      return;
    }
    var categories;
    try {
      categories = s.getMarketplaceCategories();
    } catch (e) {
      return;
    }
    list.innerHTML = "";
    for (var i = 0; i < categories.length; i++) {
      var item = document.createElement("li");
      item.textContent = categories[i];
      list.appendChild(item);
    }
  }

  /* ---------- Delivery location management ---------- */
  function locApi() {
    return window.FreshDirectDeliveryLocations || null;
  }

  function setLocFeedback(message, isError) {
    var note = byId("fd-loc-feedback");
    if (!note) {
      return;
    }
    if (!message) {
      note.textContent = "";
      note.setAttribute("hidden", "");
      note.classList.remove("is-error");
      return;
    }
    note.textContent = message;
    note.classList.toggle("is-error", !!isError);
    note.removeAttribute("hidden");
    try {
      note.focus({ preventScroll: true });
    } catch (e) {
      /* focus is best-effort */
    }
  }

  function hideLocError() {
    var box = byId("fd-loc-error");
    if (box) {
      box.textContent = "";
      box.setAttribute("hidden", "");
    }
  }

  function showLocError(message) {
    var box = byId("fd-loc-error");
    if (!box) {
      return;
    }
    box.textContent = message;
    box.removeAttribute("hidden");
  }

  function setLocFieldError(key, message) {
    var input = byId("fd-loc-" + key);
    var error = byId("fd-loc-" + key + "-error");
    if (!input) {
      return;
    }
    if (message) {
      input.setAttribute("aria-invalid", "true");
      if (error) {
        error.textContent = message;
        error.removeAttribute("hidden");
      }
    } else {
      input.removeAttribute("aria-invalid");
      if (error) {
        error.textContent = "";
        error.setAttribute("hidden", "");
      }
    }
  }

  function clearLocErrors() {
    setLocFieldError("name", "");
    setLocFieldError("fee", "");
    hideLocError();
  }

  function formatLocationFee(location) {
    return location ? fmtNaira(location.fee) : fmtNaira(null);
  }

  function buildManagedLocation(location) {
    var item = document.createElement("li");
    item.className =
      "fd-loc-admin-item" + (location.active === false ? " is-inactive" : "");
    item.setAttribute("data-location-id", location.id);

    var main = document.createElement("div");
    main.className = "fd-loc-admin-main";

    var title = document.createElement("div");
    title.className = "fd-loc-admin-title";
    var name = document.createElement("strong");
    name.textContent = location.name;
    var pill = document.createElement("span");
    pill.className =
      "fd-dash-pill " + (location.active === false ? "is-muted" : "is-ok");
    pill.textContent = location.active === false ? "Inactive" : "Active";
    title.appendChild(name);
    title.appendChild(pill);

    var meta = document.createElement("span");
    meta.className = "fd-loc-admin-meta";
    var place = [location.areas, location.city, location.state]
      .filter(Boolean)
      .join(", ");
    meta.textContent =
      (location.type === "park" ? "Park delivery" : "Doorstep delivery") +
      (place ? " \u00b7 " + place : "");

    var fee = document.createElement("span");
    fee.className = "fd-loc-admin-fee";
    fee.textContent = formatLocationFee(location);

    main.appendChild(title);
    main.appendChild(meta);
    main.appendChild(fee);

    var actions = document.createElement("div");
    actions.className = "fd-loc-admin-actions";

    var edit = document.createElement("button");
    edit.type = "button";
    edit.className = "fd-ghost-btn fd-loc-mini";
    edit.innerHTML = '<i class="fas fa-pen" aria-hidden="true"></i>Edit';
    edit.addEventListener("click", function () {
      openLocationEditor(location.id);
    });

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "fd-ghost-btn fd-loc-mini";
    toggle.innerHTML =
      '<i class="fas fa-' +
      (location.active === false ? "eye" : "eye-slash") +
      '" aria-hidden="true"></i>' +
      (location.active === false ? "Activate" : "Deactivate");
    toggle.addEventListener("click", function () {
      toggleLocation(location.id);
    });

    actions.appendChild(edit);
    actions.appendChild(toggle);
    item.appendChild(main);
    item.appendChild(actions);
    return item;
  }

  function renderManagedList(listId, locations, emptyText) {
    var list = byId(listId);
    if (!list) {
      return;
    }
    list.innerHTML = "";
    if (!locations.length) {
      list.appendChild(emptyNote(emptyText));
      return;
    }
    for (var i = 0; i < locations.length; i++) {
      list.appendChild(buildManagedLocation(locations[i]));
    }
  }

  function renderLocationManager() {
    var api = locApi();
    var door = [];
    var park = [];
    if (api && typeof api.getDeliveryLocations === "function") {
      try {
        var all = api.getDeliveryLocations({ includeInactive: true }) || [];
        for (var i = 0; i < all.length; i++) {
          if (all[i].type === "park") {
            park.push(all[i]);
          } else {
            door.push(all[i]);
          }
        }
      } catch (e) {
        /* fall through to empty lists */
      }
    }
    renderManagedList(
      "fd-loc-doorstep-list",
      door,
      "No doorstep locations are configured."
    );
    renderManagedList(
      "fd-loc-park-list-managed",
      park,
      "No park destinations are configured."
    );
    setText("fd-loc-doorstep-count", String(door.length));
    setText("fd-loc-park-count", String(park.length));
  }

  function updateLocationTypeFields() {
    var typeInput = byId("fd-loc-type");
    var type = typeInput ? typeInput.value : "doorstep";
    var doorstep = type !== "park";
    var doorstepFields = document.querySelectorAll(".fd-loc-doorstep-only");
    for (var i = 0; i < doorstepFields.length; i++) {
      if (doorstep) {
        doorstepFields[i].removeAttribute("hidden");
      } else {
        doorstepFields[i].setAttribute("hidden", "");
      }
    }
    var parkFields = document.querySelectorAll(".fd-loc-park-only");
    for (var j = 0; j < parkFields.length; j++) {
      if (doorstep) {
        parkFields[j].setAttribute("hidden", "");
      } else {
        parkFields[j].removeAttribute("hidden");
      }
    }
    var hint = byId("fd-loc-fee-hint");
    if (hint) {
      hint.textContent = "Enter the fixed fee added to the checkout total.";
    }
    var formHint = byId("fd-loc-form-hint");
    if (formHint) {
      formHint.textContent = doorstep
        ? "Doorstep locations need a fixed fee and are listed first in the checkout Delivery selector, sorted alphabetically."
        : "Park destinations need a fixed fee and are listed alphabetically at checkout.";
    }
  }

  function openLocationEditor(id) {
    var api = locApi();
    var location = null;
    if (id && api && typeof api.getDeliveryLocation === "function") {
      try {
        location = api.getDeliveryLocation(id);
      } catch (e) {
        location = null;
      }
    }
    editingLocationId = location ? location.id : "";
    var editor = byId("fd-loc-editor");
    var title = byId("fd-loc-form-title");
    if (!editor) {
      return;
    }
    clearLocErrors();
    setLocFeedback("", false);
    if (title) {
      title.textContent = location
        ? "Edit " + location.name
        : "Add a delivery location";
    }
    byId("fd-loc-type").value = location ? location.type : "doorstep";
    byId("fd-loc-name").value = location ? location.name : "";
    byId("fd-loc-areas").value = location ? location.areas || "" : "";
    byId("fd-loc-fee").value =
      location && location.fee !== null ? String(location.fee) : "";
    byId("fd-loc-city").value = location ? location.city || "" : "";
    byId("fd-loc-state").value = location ? location.state || "" : "";
    byId("fd-loc-instructions").value = location
      ? location.instructions || ""
      : "";
    byId("fd-loc-active").checked = location ? location.active !== false : true;
    updateLocationTypeFields();
    editor.removeAttribute("hidden");
    try {
      editor.scrollIntoView({ block: "nearest", behavior: "smooth" });
      byId("fd-loc-name").focus({ preventScroll: true });
    } catch (e) {
      /* focus is best-effort */
    }
  }

  function closeLocationEditor() {
    editingLocationId = "";
    var editor = byId("fd-loc-editor");
    if (editor) {
      editor.setAttribute("hidden", "");
    }
    clearLocErrors();
  }

  function saveLocation() {
    var api = locApi();
    if (!api || typeof api.upsertLocation !== "function") {
      showLocError("Delivery locations are unavailable on this page.");
      return;
    }
    clearLocErrors();
    setLocFeedback("", false);
    var type = byId("fd-loc-type").value === "park" ? "park" : "doorstep";
    var feeRaw = String(byId("fd-loc-fee").value || "").trim();
    var fee = feeRaw === "" ? null : Number(feeRaw);
    if (feeRaw !== "" && !isFinite(fee)) {
      setLocFieldError("fee", "Enter a valid delivery fee.");
      return;
    }
    var record = {
      id: editingLocationId,
      type: type,
      name: byId("fd-loc-name").value,
      areas: byId("fd-loc-areas").value,
      city: byId("fd-loc-city").value,
      state: byId("fd-loc-state").value,
      fee: fee,
      active: byId("fd-loc-active").checked,
      instructions: byId("fd-loc-instructions").value
    };
    var checked = api.validateLocation(record, { requireId: false });
    if (!checked.ok) {
      if (checked.errors.name) {
        setLocFieldError("name", checked.errors.name);
      }
      if (checked.errors.fee) {
        setLocFieldError("fee", checked.errors.fee);
      }
      showLocError("Please correct the highlighted location details.");
      var first = byId("fd-loc-name");
      try {
        first.focus();
      } catch (e) {
        /* focus is best-effort */
      }
      return;
    }
    var result;
    try {
      result = api.upsertLocation(record);
    } catch (e) {
      result = {
        ok: false,
        errors: { _form: "The location could not be saved. Please try again." }
      };
    }
    if (!result || !result.ok) {
      var errors = (result && result.errors) || {};
      if (errors.name) {
        setLocFieldError("name", errors.name);
      }
      if (errors.fee) {
        setLocFieldError("fee", errors.fee);
      }
      showLocError(
        errors._form || "Please correct the highlighted location details."
      );
      return;
    }
    var savedName = result.location ? result.location.name : record.name;
    closeLocationEditor();
    renderLocationManager();
    renderDelivery();
    setLocFeedback(
      "Saved \u201c" + savedName + "\u201d in this browser. The checkout Delivery selector uses the same store.",
      false
    );
  }

  function toggleLocation(id) {
    var api = locApi();
    if (!api || typeof api.setLocationActive !== "function") {
      return;
    }
    var location = null;
    try {
      location = api.getDeliveryLocation(id);
    } catch (e) {
      location = null;
    }
    if (!location) {
      setLocFeedback("That location could not be found.", true);
      return;
    }
    var result = api.setLocationActive(id, location.active === false);
    if (!result || !result.ok) {
      setLocFeedback(
        (result && result.errors && result.errors._form) ||
          "The location could not be updated.",
        true
      );
      return;
    }
    renderLocationManager();
    renderDelivery();
    setLocFeedback(
      "\u201c" + location.name + "\u201d is now " +
        (location.active === false ? "active" : "inactive") +
        " in the checkout Delivery selector.",
      false
    );
  }

  function wireLocationManager() {
    var add = byId("fd-loc-add");
    if (add) {
      add.addEventListener("click", function () {
        openLocationEditor(null);
      });
    }
    var save = byId("fd-loc-save");
    if (save) {
      save.addEventListener("click", saveLocation);
    }
    var cancel = byId("fd-loc-cancel");
    if (cancel) {
      cancel.addEventListener("click", function () {
        closeLocationEditor();
        setLocFeedback("", false);
      });
    }
    var type = byId("fd-loc-type");
    if (type) {
      type.addEventListener("change", updateLocationTypeFields);
    }
    var name = byId("fd-loc-name");
    if (name) {
      name.addEventListener("input", function () {
        setLocFieldError("name", "");
        hideLocError();
      });
    }
    var fee = byId("fd-loc-fee");
    if (fee) {
      fee.addEventListener("input", function () {
        setLocFieldError("fee", "");
        hideLocError();
      });
    }
    var editor = byId("fd-loc-editor");
    if (editor) {
      editor.addEventListener("keydown", function (ev) {
        if (
          ev.key === "Enter" &&
          ev.target &&
          ev.target.tagName !== "BUTTON" &&
          ev.target.tagName !== "TEXTAREA"
        ) {
          ev.preventDefault();
          saveLocation();
        }
      });
    }
  }

  /* ---------- Appearance (existing global theme preference) ---------- */
  function themeApi() {
    return window.FreshDirectTheme || null;
  }

  function paintThemeChoice() {
    var api = themeApi();
    var theme = api && typeof api.get === "function" ? api.get() : "light";
    var inputs = document.querySelectorAll('input[name="adminTheme"]');
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      var selected = input.value === theme;
      input.checked = selected;
      input.disabled = !api;
      var label = input.parentNode;
      if (label && label.classList) {
        label.classList.toggle("is-selected", selected);
      }
    }
    var note = byId("fd-settings-theme-note");
    if (note) {
      if (!api) {
        note.textContent = "The theme control is unavailable on this page.";
      } else {
        note.textContent =
          theme === "dark"
            ? "Dark mode is active in the admin on this device."
            : "Light mode is active in the admin on this device.";
      }
    }
  }

  function wireAppearance() {
    var inputs = document.querySelectorAll('input[name="adminTheme"]');
    for (var i = 0; i < inputs.length; i++) {
      inputs[i].addEventListener("change", function () {
        var api = themeApi();
        if (!api || typeof api.set !== "function") {
          return;
        }
        api.set(this.value);
        paintThemeChoice();
      });
    }
    paintThemeChoice();
    if (typeof window.MutationObserver === "function") {
      var observer = new window.MutationObserver(function () {
        paintThemeChoice();
      });
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"]
      });
    }
  }

  /* ---------- Save attempts ---------- */
  function applyErrors(result) {
    var errors = (result && result.errors) || {};
    var messages = [];
    var firstBad = null;
    for (var i = 0; i < FIELDS.length; i++) {
      var message = errors[FIELDS[i].key];
      if (message) {
        setFieldError(FIELDS[i], message);
        messages.push(FIELDS[i].label + ": " + message);
        if (!firstBad) {
          firstBad = byId(FIELDS[i].input);
        }
      }
    }
    if (errors._form) {
      messages.push(errors._form);
    }
    if (!messages.length) {
      messages.push("Your changes could not be saved. Please try again.");
    }
    showAlert(
      Object.keys(errors).length > 1 || firstBad ? "Check the highlighted fields." : "Settings were not saved.",
      messages
    );
    if (firstBad) {
      try {
        firstBad.focus();
      } catch (e) {
        /* focus is best-effort */
      }
    }
  }

  function save() {
    if (busy) {
      return;
    }
    var s = svc();
    if (!s) {
      showAlert("Settings are unavailable.", ["Reload the page and try again."]);
      return;
    }
    if (!isDirty()) {
      return;
    }
    hideAlert();
    setFeedback("", false, false);
    clearErrors();
    setBusy(true);
    var result;
    try {
      result = s.updateSettings(readForm());
    } catch (e) {
      result = {
        ok: false,
        errors: { _form: "Your changes could not be saved. Please try again." }
      };
    }
    setBusy(false);
    if (result && result.ok && result.settings) {
      fill(result.settings);
      setFeedback("Farm settings saved on this device.", false, true);
    } else {
      applyErrors(result);
    }
  }

  function discard() {
    if (busy) {
      return;
    }
    var s = svc();
    if (!s) {
      showAlert("Settings are unavailable.", ["Reload the page and try again."]);
      return;
    }
    try {
      fill(s.getSettings());
    } catch (e) {
      showError();
      return;
    }
    setFeedback("Unsaved changes discarded.", false, true);
  }

  /* ---------- In-page navigation ---------- */
  function setActiveNav(id) {
    var links = document.querySelectorAll("[data-settings-nav]");
    for (var i = 0; i < links.length; i++) {
      var active = links[i].getAttribute("data-settings-nav") === id;
      links[i].classList.toggle("is-active", active);
      if (active) {
        links[i].setAttribute("aria-current", "location");
      } else {
        links[i].removeAttribute("aria-current");
      }
    }
  }

  function updateActiveNav() {
    var sections = document.querySelectorAll("[data-settings-section]");
    if (!sections.length) {
      return;
    }
    var threshold = 110;
    var current = sections[0].id;
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].getBoundingClientRect().top <= threshold) {
        current = sections[i].id;
      }
    }
    setActiveNav(current);
  }

  function queueActiveNav() {
    if (scrollQueued) {
      return;
    }
    scrollQueued = true;
    window.requestAnimationFrame(function () {
      scrollQueued = false;
      updateActiveNav();
    });
  }

  function wireNav() {
    if (navWired) {
      return;
    }
    navWired = true;
    var links = document.querySelectorAll("[data-settings-nav]");
    for (var i = 0; i < links.length; i++) {
      links[i].addEventListener("click", function () {
        setActiveNav(this.getAttribute("data-settings-nav"));
      });
    }
    window.addEventListener("scroll", queueActiveNav, { passive: true });
    window.addEventListener("resize", queueActiveNav);
    updateActiveNav();
  }

  /* ---------- Wiring ---------- */
  function wireForm() {
    var form = byId("fd-settings-form");
    var discardBtn = byId("fd-settings-discard");
    if (form) {
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        save();
      });
    }
    if (discardBtn) {
      discardBtn.addEventListener("click", discard);
    }
    for (var i = 0; i < FIELDS.length; i++) {
      var input = byId(FIELDS[i].input);
      if (input) {
        input.addEventListener("input", function () {
          var field = fieldByInput(this.id);
          setFieldError(field, "");
          hideAlert();
          setFeedback("", false, false);
          paintDirty();
          if (field && field.key === "description") {
            paintDescription();
          }
        });
      }
    }
  }

  function wireRetry() {
    var retry = byId("fd-settings-retry");
    if (retry) {
      retry.addEventListener("click", load);
    }
  }

  function wireUnload() {
    window.addEventListener("beforeunload", function (ev) {
      if (!isDirty()) {
        return;
      }
      ev.preventDefault();
      ev.returnValue = "";
      return "";
    });
  }

  function load() {
    var s = svc();
    if (!s || typeof s.getSettings !== "function") {
      showError();
      return;
    }
    showLoading();
    var settings;
    try {
      settings = s.getSettings();
    } catch (e) {
      showError();
      return;
    }
    fill(settings);
    renderBrand();
    renderDelivery();
    renderLocationManager();
    renderCategories();
    paintThemeChoice();
    showContent();
    wireNav();
  }

  function init() {
    if (!byId("fd-settings-form")) {
      return;
    }
    wireForm();
    wireRetry();
    wireUnload();
    wireAppearance();
    wireLocationManager();
    load();
  }

  window.FreshDirectAdminSettingsUI = {
    load: load,
    esc: esc,
    fields: FIELDS.slice(),
    isDirty: isDirty
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
