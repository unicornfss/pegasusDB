(function () {
  const DEBUG = false;
  const log = (...args) => { if (DEBUG) console.log("[places]", ...args); };

  function ensurePacZIndex() {
    if (document.getElementById("places-pac-zindex")) return;
    const style = document.createElement("style");
    style.id = "places-pac-zindex";
    style.textContent = ".pac-container { z-index: 10000 !important; }";
    document.head.appendChild(style);
  }

  function component(place, type, part = "long_name") {
    const match = (place.address_components || []).find((c) => c.types.includes(type));
    return match ? match[part] : "";
  }

  function parsePlace(place) {
    const streetNumber = component(place, "street_number");
    const route = component(place, "route");
    const street =
      [streetNumber, route].filter(Boolean).join(" ") ||
      component(place, "street_address") ||
      "";

    const town =
      component(place, "postal_town") ||
      component(place, "locality") ||
      component(place, "administrative_area_level_2");

    const postcode = component(place, "postal_code");

    let propertyName = component(place, "premise") || component(place, "subpremise") || "";
    const placeName = (place.name || "").trim();
    const types = place.types || [];

    if (!propertyName && placeName) {
      const isNamedPlace = types.some((t) =>
        ["establishment", "point_of_interest", "premise", "subpremise"].includes(t)
      );
      const looksLikeStreetOnly =
        (street && (placeName === street || placeName.startsWith(street + " "))) ||
        /^\d+\s/.test(placeName);

      if (isNamedPlace && !looksLikeStreetOnly) {
        propertyName = placeName;
      } else if (
        placeName &&
        route &&
        placeName !== route &&
        !looksLikeStreetOnly &&
        (place.formatted_address || "").split(",")[0].trim() === placeName
      ) {
        propertyName = placeName;
      }
    }

    return { street, town, postcode, propertyName };
  }

  function resolveField(form, selectorOrEl) {
    if (!selectorOrEl) return null;
    if (selectorOrEl instanceof Element) return selectorOrEl;
    if (typeof selectorOrEl === "string") {
      return form.querySelector(selectorOrEl) || document.querySelector(selectorOrEl);
    }
    return null;
  }

  function applyPlaceToFields(place, fieldMap) {
    if (!place || !fieldMap) return;
    const parsed = parsePlace(place);

    const streetEl = resolveField(document, fieldMap.addressLine);
    const townEl = resolveField(document, fieldMap.town);
    const postcodeEl = resolveField(document, fieldMap.postcode);
    const propertyEl = resolveField(document, fieldMap.propertyName);

    if (streetEl) {
      streetEl.value = parsed.street || streetEl.value;
      if (!streetEl.value && place.formatted_address) {
        streetEl.value = place.formatted_address.split(",")[0].trim();
      }
    }
    if (townEl) townEl.value = parsed.town || townEl.value;
    if (postcodeEl) postcodeEl.value = parsed.postcode || postcodeEl.value;
    if (propertyEl && parsed.propertyName) propertyEl.value = parsed.propertyName;

    return parsed;
  }

  function attachPlacesAutocomplete(input, fieldMap, options) {
    options = options || {};
    if (!input) return null;
    if (!(window.google && google.maps && google.maps.places)) return null;

    const modal = input.closest(".modal");
    if (modal && !modal.classList.contains("show") && !options.allowHidden) {
      return null;
    }

    if (input.dataset.placesAttached === "1" && !options.reinit) {
      return input._placesAutocomplete || null;
    }

    if (options.reinit && input.dataset.placesAttached === "1") {
      const clone = input.cloneNode(true);
      clone.value = input.value;
      clone.removeAttribute("data-places-attached");
      delete clone.dataset.placesAttached;
      delete clone.dataset.placesVisibleAttached;
      delete clone._placesAutocomplete;
      input.parentNode.replaceChild(clone, input);
      input = clone;
    }

    ensurePacZIndex();

    const ac = new google.maps.places.Autocomplete(input, {
      fields: ["address_components", "formatted_address", "name", "types"],
      componentRestrictions: { country: "gb" },
    });

    ac.addListener("place_changed", () => {
      const place = ac.getPlace();
      if (!place) return;
      applyPlaceToFields(place, fieldMap);
    });

    input._placesAutocomplete = ac;
    input.dataset.placesAttached = "1";
    log("Autocomplete attached to", input.id || input.name || input);
    return ac;
  }

  function defaultFieldMapForInput(input) {
    const form = input.form || document;
    const byId = (id) => form.querySelector(`#${id}`) || document.querySelector(`#${id}`);
    const byName = (name) => form.querySelector(`[name="${name}"]`);

    return {
      addressLine: input,
      town: byId("id_town") || byName("town"),
      postcode: byId("id_postcode") || byName("postcode"),
      propertyName: byId("id_property_name") || byName("property_name"),
    };
  }

  function initStandardForms() {
    const selectors = [
      "#id_address_line",
      "#id_business_address",
      "input[name='address_line']",
    ];
    const seen = new Set();
    const inputs = selectors
      .flatMap((sel) => Array.from(document.querySelectorAll(sel)))
      .filter((input) => {
        if (!input || seen.has(input)) return false;
        const modal = input.closest(".modal");
        if (modal && !modal.classList.contains("show")) return false;
        seen.add(input);
        return true;
      });

    if (!inputs.length) {
      log("No address inputs found");
      return;
    }

    inputs.forEach((input) => attachPlacesAutocomplete(input, defaultFieldMapForInput(input)));
  }

  function waitFor(cond, cb, tries = 40, interval = 250) {
    if (cond()) return cb();
    if (tries <= 0) return log("Timeout waiting for condition");
    setTimeout(() => waitFor(cond, cb, tries - 1, interval), interval);
  }

  window.TrainingPlaces = {
    parsePlace,
    applyPlaceToFields,
    attach: attachPlacesAutocomplete,
  };

  document.addEventListener("gmaps:ready", () => {
    if (!(window.google && google.maps && google.maps.places)) {
      return waitFor(() => (window.google && google.maps && google.maps.places), initStandardForms);
    }
    initStandardForms();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      if (window.google && google.maps && google.maps.places) initStandardForms();
    });
  } else if (window.google && google.maps && google.maps.places) {
    initStandardForms();
  }
})();
