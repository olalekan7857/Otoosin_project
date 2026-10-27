/* ==========================================================================
   O’TOOSIN Farms Admin — Settings source boundary
   --------------------------------------------------------------------------
   Vanilla JS, no dependencies, no framework. Admin-scoped: never touches
   the customer cart store and never loads fresh-direct.js, so customer
   state cannot leak into the admin area.

   CANONICAL SETTINGS SHAPE:
     { businessName, contactPhone, whatsapp, address, description }

   Editable values are validated here and kept in this browser
   (localStorage "freshdirect_admin_settings_v1"). updateSettings() reports
   the genuine result: success means "saved in this browser", never a
   database claim. The admin order follow-up link reads getWhatsAppNumber(),
   so a saved WhatsApp change genuinely takes effect there.

   DELIVERY AND PICKUP:
     Delivery locations come from the shared
     window.FreshDirectDeliveryLocations boundary
     (assets/js/fd-delivery-locations.js), which is also loaded by checkout.
     The Settings page can add, edit, activate and deactivate locations
     through that boundary; getDeliveryInfo() exposes the same records for
     the read-only summary. Pickup locations stay separate. Pickup orders
     have no delivery fee. Doorstep fees come from the selected location.
     Park charges without a confirmed fee stay marked as requiring
     confirmation and are never treated as free delivery.

   DJANGO INTEGRATION (later stage, no settings-UI rebuild needed):
     - Replace getSettings()/updateSettings() with API calls that resolve
       the SAME canonical settings shape and the SAME result shape
       { ok, settings?, errors? }.
     - Replace getDeliveryInfo() with the backend delivery configuration
       using the same arrays, so the existing Settings renderers are reused.
     - Keep this file's public signatures so fd-admin-settings.js and
       fd-admin-orders-data.js are reused untouched.
     - Do NOT hardcode endpoint URLs here.
   ========================================================================== */
(function () {
  "use strict";

  var STORE_KEY = "freshdirect_admin_settings_v1";

  /* Central store number (digits only). Mirrors
     FRESH_DIRECT.whatsappNumber (assets/js/fresh-direct.js), which mirrors
     the future Django setting WHATSAPP_NUMBER. Never add a second number:
     overrides live in the settings record above. */
  var CENTRAL_WHATSAPP = "2349011058873";

  var BRAND_SLOGAN =
    "O’TOOSIN Farms - delivering safe, healthy, and nutritious foods at your doorstep . . .";

  var BRAND_LOGO = {
    src: "assets/img/harvest_castle/of_favicon.png",
    alt: "O’TOOSIN Farms",
    reference: "assets/img/harvest_castle/of_favicon.png"
  };

  var MARKETPLACE_CATEGORIES = [
    "Meats",
    "Fish",
    "Live Animals",
    "Eggs",
    "Veggies",
    "Fruits"
  ];

  var DELIVERY_INFO = {
    coverage:
      "Doorstep delivery is currently limited to Abeokuta. Park delivery serves approved destinations such as Lagos, Ibadan and Ijebu.",
    doorstep:
      "Choose a delivery location at checkout. The selected doorstep fee is added to the order total.",
    park:
      "Park delivery is available to approved destinations. The selected park delivery fee is added to the order total.",
    pickup:
      "Choose Mummy-D Stores at checkout. Pickup orders have no delivery fee.",
    payment:
      "Doorstep and park delivery fees are included in the checkout total, and pickup has no delivery fee. Payment is completed securely through the website at checkout."
  };

  function locationsApi() {
    return typeof window !== "undefined"
      ? window.FreshDirectDeliveryLocations || null
      : null;
  }

  function deliveryLocations() {
    var api = locationsApi();
    if (!api || typeof api.getDeliveryLocations !== "function") {
      return [];
    }
    try {
      return api.getDeliveryLocations({ includeInactive: true }) || [];
    } catch (e) {
      return [];
    }
  }

  function pickupLocations() {
    var api = locationsApi();
    if (!api || typeof api.getPickupLocations !== "function") {
      return [];
    }
    try {
      return api.getPickupLocations() || [];
    } catch (e) {
      return [];
    }
  }

  var DEFAULTS = {
    businessName: "O’TOOSIN Farms",
    contactPhone: "",
    whatsapp: CENTRAL_WHATSAPP,
    address: "Mummy-D Stores, Beside FUNAAB MANCOT Park, Camp, Abeokuta",
    description:
      "Shop meats, fish, live animals, eggs, veggies and fruits from O’TOOSIN Farms. Choose each item and its unit, then select doorstep delivery, park delivery or pickup at checkout."
  };

  /* Exact previous defaults are replaced on read so stale branding or
     meat-only copy cannot survive a manual correction. Custom edits are
     always preserved. */
  var LEGACY_BUSINESS_NAMES = ["Harvest Castle", "O'Toosin Farms"];
  var LEGACY_ADDRESSES = [
    "No. 89, behind Foursquare Church, FUNAAB Alabata Road, Camp, Abeokuta."
  ];
  var LEGACY_DESCRIPTIONS = [
    "Farm produce sold directly to you. Shop online on the website, or order through WhatsApp \u2014 serving the FUNAAB and Abeokuta community.",
    "A meat shop selling pork, chicken, turkey, beef, goat meat and fish. Browse by meat type and state, order by the kilogram, and choose Pay Now or Pay on Delivery."
  ];

  var FIELDS = ["businessName", "contactPhone", "whatsapp", "address", "description"];

  function asText(value) {
    return typeof value === "string" ? value : "";
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

  function readStored() {
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
      var saved = (data && data.settings) || {};
      var out = {};
      for (var i = 0; i < FIELDS.length; i++) {
        if (typeof saved[FIELDS[i]] === "string") {
          out[FIELDS[i]] = saved[FIELDS[i]];
        }
      }
      /* Migrate stale branding without inventing a new store record. */
      var migrated = false;
      if (LEGACY_BUSINESS_NAMES.indexOf(out.businessName) !== -1) {
        delete out.businessName;
        migrated = true;
      }
      if (LEGACY_ADDRESSES.indexOf(out.address) !== -1) {
        delete out.address;
        migrated = true;
      }
      if (LEGACY_DESCRIPTIONS.indexOf(out.description) !== -1) {
        delete out.description;
        migrated = true;
      }
      if (migrated) {
        writeStored(out);
      }
      return out;
    } catch (e) {
      return {};
    }
  }

  function writeStored(settings) {
    var store = localStore();
    if (!store) {
      return false;
    }
    try {
      store.setItem(STORE_KEY, JSON.stringify({ v: 1, settings: settings }));
      return true;
    } catch (e) {
      return false;
    }
  }

  /* ---------- Normalization ---------- */
  /* WhatsApp / phone input tolerance: spaces, dashes and brackets are
     ignored; a leading 0 becomes the 234 country code; a leading +
     is dropped. Stored canonically as digits for wa.me links. */
  function normalizePhone(value) {
    var digits = asText(value).replace(/[^\d+]/g, "");
    if (digits.charAt(0) === "+") {
      digits = digits.slice(1);
    }
    digits = digits.replace(/\D/g, "");
    if (/^0\d+/.test(digits)) {
      digits = "234" + digits.slice(1);
    }
    return digits;
  }

  function isNigerianMobile(digits) {
    return /^234[789][01]\d{8}$/.test(digits);
  }

  /* ---------- Validation (client-side only; Django re-validates) ---------- */
  function validate(settings) {
    var errors = {};
    var name = asText(settings.businessName).trim();
    if (!name) {
      errors.businessName = "Enter your business name.";
    } else if (name.length < 2) {
      errors.businessName = "Business name must be at least 2 characters.";
    } else if (name.length > 80) {
      errors.businessName = "Business name must be 80 characters or fewer.";
    }
    var phone = asText(settings.contactPhone).trim();
    if (phone && !isNigerianMobile(normalizePhone(phone))) {
      errors.contactPhone = "Enter a valid Nigerian phone number, or leave it empty.";
    }
    var wa = asText(settings.whatsapp).trim();
    if (!wa) {
      errors.whatsapp = "Enter the WhatsApp number customers should reach.";
    } else if (!isNigerianMobile(normalizePhone(wa))) {
      errors.whatsapp = "Enter a valid Nigerian WhatsApp number.";
    }
    var address = asText(settings.address).trim();
    if (!address) {
      errors.address = "Enter your business address.";
    } else if (address.length < 5) {
      errors.address = "Business address looks too short.";
    } else if (address.length > 300) {
      errors.address = "Business address must be 300 characters or fewer.";
    }
    var desc = asText(settings.description).trim();
    if (!desc) {
      errors.description = "Enter a short storefront introduction.";
    } else if (desc.length < 20) {
      errors.description = "Storefront introduction looks too short.";
    } else if (desc.length > 500) {
      errors.description = "Storefront introduction must be 500 characters or fewer.";
    }
    return { ok: Object.keys(errors).length === 0, errors: errors };
  }

  function canonicalize(settings) {
    return {
      businessName: asText(settings.businessName).trim(),
      contactPhone: asText(settings.contactPhone).trim(),
      whatsapp: normalizePhone(asText(settings.whatsapp)),
      address: asText(settings.address).trim(),
      description: asText(settings.description).trim()
    };
  }

  /* ---------- Public boundary ---------- */

  /* Current settings: established defaults overlaid with anything the
     owner genuinely saved in this browser. Always returns a fresh
     object in the canonical shape. */
  function getSettings() {
    var out = {};
    for (var i = 0; i < FIELDS.length; i++) {
      out[FIELDS[i]] = DEFAULTS[FIELDS[i]];
    }
    var stored = readStored();
    var keys = Object.keys(stored);
    for (var j = 0; j < keys.length; j++) {
      if (FIELDS.indexOf(keys[j]) !== -1) {
        out[keys[j]] = stored[keys[j]];
      }
    }
    return canonicalizeLight(out);
  }

  /* Defaults are already canonical except stored overrides, which are
     re-validated on read so a hand-edited record can never inject a
     malformed WhatsApp number into admin links. */
  function canonicalizeLight(settings) {
    var out = {};
    for (var i = 0; i < FIELDS.length; i++) {
      out[FIELDS[i]] = asText(settings[FIELDS[i]]);
    }
    if (out.whatsapp && !isNigerianMobile(out.whatsapp)) {
      var fixed = normalizePhone(out.whatsapp);
      out.whatsapp = isNigerianMobile(fixed) ? fixed : CENTRAL_WHATSAPP;
    }
    if (!out.whatsapp) {
      out.whatsapp = CENTRAL_WHATSAPP;
    }
    return out;
  }

  /* Validate -> persist through the settings service.
     Django stage: PATCH the payload and resolve the same result shape
     { ok, settings?, errors? }. */
  function updateSettings(patch) {
    var next = getSettings();
    var incoming = patch && typeof patch === "object" ? patch : {};
    for (var i = 0; i < FIELDS.length; i++) {
      if (typeof incoming[FIELDS[i]] === "string") {
        next[FIELDS[i]] = incoming[FIELDS[i]];
      }
    }
    var checked = validate(next);
    if (!checked.ok) {
      return { ok: false, settings: null, errors: checked.errors };
    }
    var canonical = canonicalize(next);
    if (!writeStored(canonical)) {
      return {
        ok: false,
        settings: null,
        errors: {
          _form: "Your changes could not be saved. Please try again."
        }
      };
    }
    /* Read back so success is only reported for a genuinely stored change. */
    var verify = getSettings();
    for (var j = 0; j < FIELDS.length; j++) {
      if (verify[FIELDS[j]] !== canonical[FIELDS[j]]) {
        return {
          ok: false,
          settings: null,
          errors: {
            _form: "Your changes could not be saved. Please try again."
          }
        };
      }
    }
    return { ok: true, settings: verify, errors: {} };
  }

  /* The single WhatsApp source for admin surfaces (order follow-ups).
     Falls back to the centralized digits when nothing valid is stored. */
  function getWhatsAppNumber() {
    try {
      var current = getSettings();
      if (current.whatsapp && isNigerianMobile(current.whatsapp)) {
        return current.whatsapp;
      }
    } catch (e) {
      /* fall through to the centralized digits */
    }
    return CENTRAL_WHATSAPP;
  }

  function getDeliveryInfo() {
    var locations = deliveryLocations();
    var zones = [];
    var parks = [];
    for (var i = 0; i < locations.length; i++) {
      var location = locations[i];
      if (location.type === "park") {
        parks.push({
          id: location.id,
          name: location.name,
          fee: location.fee,
          active: location.active,
          city: location.city,
          state: location.state
        });
      } else {
        zones.push({
          id: location.id,
          name: location.name,
          areas: location.areas,
          fee: location.fee,
          active: location.active,
          city: location.city,
          state: location.state
        });
      }
    }
    return {
      coverage: DELIVERY_INFO.coverage,
      doorstep: DELIVERY_INFO.doorstep,
      park: DELIVERY_INFO.park,
      pickup: DELIVERY_INFO.pickup,
      payment: DELIVERY_INFO.payment,
      zones: zones,
      parkDestinations: parks,
      pickupLocations: pickupLocations()
    };
  }

  function getBrandInfo() {
    return {
      name: DEFAULTS.businessName,
      slogan: BRAND_SLOGAN,
      logo: {
        src: BRAND_LOGO.src,
        alt: BRAND_LOGO.alt,
        reference: BRAND_LOGO.reference
      }
    };
  }

  function getMarketplaceCategories() {
    return MARKETPLACE_CATEGORIES.slice();
  }

  if (typeof window !== "undefined") {
    window.FreshDirectAdminSettings = {
      source: "local-record",
      sourceNote:
        "Store record kept in this browser. Replace internals with Django settings endpoints.",
      storeKey: STORE_KEY,
      fields: FIELDS.slice(),
      centralWhatsApp: CENTRAL_WHATSAPP,
      getSettings: getSettings,
      updateSettings: updateSettings,
      validate: validate,
      normalizePhone: normalizePhone,
      getWhatsAppNumber: getWhatsAppNumber,
      getDeliveryInfo: getDeliveryInfo,
      getBrandInfo: getBrandInfo,
      getMarketplaceCategories: getMarketplaceCategories
    };
  }
})();
