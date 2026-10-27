/* ==========================================================================
   O’TOOSIN Farms — Shared delivery-location boundary
   --------------------------------------------------------------------------
   Plain browser JavaScript with no dependencies. This file is the single
   source of delivery locations used by checkout.html AND the custom admin
   Settings page.

   Records are kept in this browser under
   localStorage "freshdirect_delivery_locations_v1" so the admin and the
   checkout read the same identifiers, fees and availability. This is a
   frontend demonstration store, not a database and not shared across
   devices. Django can later replace the read/write internals while keeping
   the public shape below.

   DELIVERY LOCATION SHAPE:
     {
       id, type: "doorstep" | "park", name, areas, city, state,
       fee: number, active: boolean, order: number, instructions
     }

   Every delivery location has a fee. Park fees are frontend demonstration
   prices until the admin pages are connected to the backend.

   PICKUP LOCATIONS stay separate from delivery locations. They are exposed
   read-only here and are never included in the checkout Delivery dropdown.
   ========================================================================== */
(function () {
  "use strict";

  var STORE_KEY = "freshdirect_delivery_locations_v1";

  var DEFAULT_DELIVERY_LOCATIONS = [
    {
      id: "camp",
      type: "doorstep",
      name: "Camp",
      areas: "Fatola, Apakila, Surulere",
      city: "Abeokuta",
      state: "Ogun",
      fee: 5000,
      active: true,
      order: 1,
      instructions: ""
    },
    {
      id: "obantoko",
      type: "doorstep",
      name: "Obantoko",
      areas: "Eleweran, Somorin, Odoeran",
      city: "Abeokuta",
      state: "Ogun",
      fee: 10000,
      active: true,
      order: 2,
      instructions: ""
    },
    {
      id: "lagos",
      type: "park",
      name: "Lagos",
      areas: "",
      city: "Lagos",
      state: "Lagos",
      fee: 12000,
      active: true,
      order: 3,
      instructions: "Our team confirms the approved Lagos receiving park before dispatch."
    },
    {
      id: "ibadan",
      type: "park",
      name: "Ibadan",
      areas: "",
      city: "Ibadan",
      state: "Oyo",
      fee: 8000,
      active: true,
      order: 4,
      instructions: "Our team confirms the approved Ibadan receiving park before dispatch."
    },
    {
      id: "ijebu",
      type: "park",
      name: "Ijebu",
      areas: "",
      city: "Ijebu-Ode",
      state: "Ogun",
      fee: 6000,
      active: true,
      order: 5,
      instructions: "Our team confirms the approved Ijebu receiving park before dispatch."
    }
  ];

  var DEFAULT_PICKUP_LOCATIONS = [
    {
      id: "mummy-d-stores",
      name: "Mummy-D Stores",
      address: "Beside FUNAAB MANCOT Park, Camp, Abeokuta",
      active: true
    }
  ];

  function asText(value) {
    return typeof value === "string" ? value : value == null ? "" : String(value);
  }

  function asNumber(value) {
    if (value === null || value === undefined || value === "") {
      return null;
    }
    var number = Number(value);
    return isFinite(number) ? number : null;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

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

  function normalizeLocation(record) {
    var input = record && typeof record === "object" ? record : {};
    var type = input.type === "park" ? "park" : "doorstep";
    return {
      id: asText(input.id).trim(),
      type: type,
      name: asText(input.name).trim(),
      areas: asText(input.areas).trim(),
      city: asText(input.city).trim(),
      state: asText(input.state).trim(),
      fee: asNumber(input.fee),
      active: input.active === false ? false : true,
      order: asNumber(input.order) === null ? 999 : asNumber(input.order),
      instructions: asText(input.instructions).trim()
    };
  }

  function normalizeList(list) {
    var out = [];
    if (!Array.isArray(list)) {
      return out;
    }
    for (var i = 0; i < list.length; i++) {
      var item = normalizeLocation(list[i]);
      if (item.id && item.name) {
        out.push(item);
      }
    }
    return out;
  }

  function defaultFeeFor(location) {
    for (var i = 0; i < DEFAULT_DELIVERY_LOCATIONS.length; i++) {
      if (DEFAULT_DELIVERY_LOCATIONS[i].id === location.id) {
        return DEFAULT_DELIVERY_LOCATIONS[i].fee;
      }
    }
    return location.type === "park" ? 8000 : 5000;
  }

  function readStored() {
    var store = localStore();
    if (!store) {
      return null;
    }
    try {
      var raw = store.getItem(STORE_KEY);
      if (!raw) {
        return null;
      }
      var data = JSON.parse(raw);
      if (!data || typeof data !== "object") {
        return null;
      }
      var delivery = normalizeList(data.delivery);
      for (var d = 0; d < delivery.length; d++) {
        if (delivery[d].fee === null) {
          delivery[d].fee = defaultFeeFor(delivery[d]);
        }
      }
      var pickup = Array.isArray(data.pickup)
        ? data.pickup
            .map(function (item) {
              return {
                id: asText(item && item.id).trim(),
                name: asText(item && item.name).trim(),
                address: asText(item && item.address).trim(),
                active: !(item && item.active === false)
              };
            })
            .filter(function (item) {
              return item.id && item.name;
            })
        : [];
      if (!delivery.length) {
        return null;
      }
      return {
        delivery: delivery,
        pickup: pickup.length ? pickup : clone(DEFAULT_PICKUP_LOCATIONS)
      };
    } catch (e) {
      return null;
    }
  }

  function writeStored(delivery, pickup) {
    var store = localStore();
    if (!store) {
      return false;
    }
    try {
      store.setItem(
        STORE_KEY,
        JSON.stringify({ v: 1, delivery: delivery, pickup: pickup })
      );
      return true;
    } catch (e) {
      return false;
    }
  }

  function defaultDelivery() {
    return clone(DEFAULT_DELIVERY_LOCATIONS);
  }

  function currentStore() {
    var stored = readStored();
    if (stored) {
      return stored;
    }
    return {
      delivery: defaultDelivery(),
      pickup: clone(DEFAULT_PICKUP_LOCATIONS)
    };
  }

  function sortLocations(list) {
    var copy = list.slice();
    copy.sort(function (a, b) {
      var typeRank = function (item) {
        return item.type === "doorstep" ? 0 : 1;
      };
      var typeDiff = typeRank(a) - typeRank(b);
      if (typeDiff !== 0) {
        return typeDiff;
      }
      return a.name.localeCompare(b.name);
    });
    return copy;
  }

  function getDeliveryLocations(options) {
    var opts = options || {};
    var list = currentStore().delivery;
    if (!opts.includeInactive) {
      list = list.filter(function (item) {
        return item.active;
      });
    }
    return sortLocations(clone(list));
  }

  function getActiveDeliveryLocations() {
    return getDeliveryLocations();
  }

  function getDeliveryLocation(id) {
    var list = currentStore().delivery;
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        return clone(list[i]);
      }
    }
    return null;
  }

  function getPickupLocations() {
    var list = currentStore().pickup.filter(function (item) {
      return item.active !== false;
    });
    return clone(list);
  }

  function slugify(value) {
    return asText(value)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 48);
  }

  function uniqueId(type, name, list) {
    var base = (type === "park" ? "park-" : "doorstep-") + (slugify(name) || "location");
    var id = base;
    var index = 2;
    var exists = function (candidate) {
      for (var i = 0; i < list.length; i++) {
        if (list[i].id === candidate) {
          return true;
        }
      }
      return false;
    };
    while (exists(id)) {
      id = base + "-" + index;
      index += 1;
    }
    return id;
  }

  function validateLocation(record, options) {
    var opts = options || {};
    var item = normalizeLocation(record);
    var errors = {};
    if (!item.name || item.name.length < 2) {
      errors.name = "Enter a location name with at least 2 characters.";
    } else if (item.name.length > 80) {
      errors.name = "Location name must be 80 characters or fewer.";
    }
    if (item.fee === null) {
      errors.fee = "Enter the delivery fee.";
    } else if (item.fee < 0) {
      errors.fee = "Delivery fee cannot be negative.";
    }
    if (item.fee !== null && item.fee > 1000000) {
      errors.fee = "That delivery fee looks too high. Check the amount.";
    }
    if (item.areas.length > 200) {
      errors.areas = "Areas covered must be 200 characters or fewer.";
    }
    if (item.city.length > 80) {
      errors.city = "City must be 80 characters or fewer.";
    }
    if (item.state.length > 80) {
      errors.state = "State must be 80 characters or fewer.";
    }
    if (item.instructions.length > 300) {
      errors.instructions = "Customer instructions must be 300 characters or fewer.";
    }
    if (opts.requireId && !item.id) {
      errors.id = "The location identifier is missing.";
    }
    return {
      ok: Object.keys(errors).length === 0,
      errors: errors,
      location: item
    };
  }

  function saveDeliveryLocations(list) {
    var checked = normalizeList(list);
    if (!checked.length) {
      return {
        ok: false,
        errors: { _form: "Keep at least one delivery location configured." }
      };
    }
    var seen = {};
    for (var i = 0; i < checked.length; i++) {
      var result = validateLocation(checked[i], { requireId: true });
      if (!result.ok) {
        return { ok: false, errors: result.errors };
      }
      if (seen[checked[i].id]) {
        return {
          ok: false,
          errors: { _form: "Two locations share the same identifier." }
        };
      }
      seen[checked[i].id] = true;
    }
    var store = currentStore();
    if (!writeStored(checked, store.pickup)) {
      return {
        ok: false,
        errors: { _form: "Your changes could not be saved in this browser." }
      };
    }
    var verify = readStored();
    if (!verify || verify.delivery.length !== checked.length) {
      return {
        ok: false,
        errors: { _form: "Your changes could not be saved in this browser." }
      };
    }
    return {
      ok: true,
      errors: {},
      locations: sortLocations(clone(verify.delivery))
    };
  }

  function upsertLocation(record) {
    var store = currentStore();
    var list = store.delivery;
    var input = normalizeLocation(record);
    var index = -1;
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === input.id) {
        index = i;
        break;
      }
    }
    if (!input.id) {
      input.id = uniqueId(input.type, input.name, list);
      input.order = list.length
        ? Math.max.apply(
            null,
            list.map(function (item) {
              return item.order;
            })
          ) + 1
        : 1;
    }
    if (index === -1) {
      index = -1;
    } else {
      input.order = list[index].order;
    }
    var checked = validateLocation(input, { requireId: true });
    if (!checked.ok) {
      return { ok: false, errors: checked.errors, location: null };
    }
    if (index >= 0) {
      list[index] = checked.location;
    } else {
      list.push(checked.location);
    }
    var saved = saveDeliveryLocations(list);
    if (!saved.ok) {
      return { ok: false, errors: saved.errors, location: null };
    }
    return {
      ok: true,
      errors: {},
      location: clone(checked.location),
      locations: saved.locations
    };
  }

  function setLocationActive(id, active) {
    var store = currentStore();
    var list = store.delivery;
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        list[i].active = !!active;
        var saved = saveDeliveryLocations(list);
        if (!saved.ok) {
          return { ok: false, errors: saved.errors, location: null };
        }
        return { ok: true, errors: {}, location: clone(list[i]), locations: saved.locations };
      }
    }
    return {
      ok: false,
      errors: { _form: "That location could not be found." },
      location: null
    };
  }

  if (typeof window !== "undefined") {
    window.FreshDirectDeliveryLocations = {
      source: "local-record",
      sourceNote:
        "Delivery locations are kept in this browser. Replace the internals with Django delivery endpoints later.",
      storeKey: STORE_KEY,
      types: ["doorstep", "park"],
      getDeliveryLocations: getDeliveryLocations,
      getActiveDeliveryLocations: getActiveDeliveryLocations,
      getDeliveryLocation: getDeliveryLocation,
      getPickupLocations: getPickupLocations,
      validateLocation: validateLocation,
      saveDeliveryLocations: saveDeliveryLocations,
      upsertLocation: upsertLocation,
      setLocationActive: setLocationActive
    };
  }
})();
