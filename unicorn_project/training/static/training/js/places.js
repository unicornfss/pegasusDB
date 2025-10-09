(function () {
  const DEBUG = false;
  const log = (...args) => { if (DEBUG) console.log("[places]", ...args); };

  function waitFor(cond, cb, tries = 40, interval = 250) {
    if (cond()) return cb();
    if (tries <= 0) return log("Timeout waiting for condition");
    setTimeout(() => waitFor(cond, cb, tries - 1, interval), interval);
  }

  function attachAutocompleteTo(input) {
    if (!input) return;
    const want = ["address_components", "formatted_address", "name"];
    const ac = new google.maps.places.Autocomplete(input, {
      fields: want,
      types: ["address"],
      componentRestrictions: { country: "gb" }, // adjust as needed
    });
    ac.addListener("place_changed", () => {
      const place = ac.getPlace();
      if (!place) return;

      const get = (type, part = "long_name") => {
        const c = (place.address_components || []).find(x => x.types.includes(type));
        return c ? c[part] : "";
      };
      const streetNumber = get("street_number");
      const route = get("route");
      const town = get("postal_town") || get("locality");
      const postcode = get("postal_code");

      const street =
        [streetNumber, route].filter(Boolean).join(" ") ||
        (place.name && route ? `${place.name} ${route}` : input.value);

      // Find sibling fields by id or name:
      const form = input.form || document;
      const byId = id => form.querySelector(`#${id}`);
      const byName = name => form.querySelector(`[name="${name}"]`);

      const streetEl   = byId("id_address_line") || byName("address_line");
      const townEl     = byId("id_town")         || byName("town");
      const postcodeEl = byId("id_postcode")     || byName("postcode");

      if (streetEl)   streetEl.value = street || streetEl.value;
      if (townEl)     townEl.value = town || townEl.value;
      if (postcodeEl) postcodeEl.value = postcode || postcodeEl.value;
    });
  }

  function init() {
    // Hit the most common field ids/names you’re using in Business, Location, Instructor forms
    const candidates = [
      "#id_address_line",
      "input[name='address_line']",
      // add more selectors here if any form uses a different name/id
    ];
    const inputs = candidates
      .map(sel => Array.from(document.querySelectorAll(sel)))
      .flat()
      .filter(Boolean);

    if (!inputs.length) {
      log("No address inputs found");
      return;
    }
    inputs.forEach(attachAutocompleteTo);
    log("Autocomplete attached to", inputs.length, "input(s)");
  }

  // Run when Maps is ready, or when the script tag finished loading
  document.addEventListener("gmaps:ready", () => {
    if (!(window.google && google.maps && google.maps.places)) {
      return waitFor(() => (window.google && google.maps && google.maps.places), init);
    }
    init();
  });

  // Also run on DOM ready if Google script was already loaded/cached
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      if (window.google && google.maps && google.maps.places) init();
    });
  } else {
    if (window.google && google.maps && google.maps.places) init();
  }
})();
