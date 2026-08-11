(function () {
  const FIELD_IDS = [
    "add-loc-name",
    "add-loc-property-name",
    "add-loc-address",
    "add-loc-town",
    "add-loc-postcode",
    "add-loc-contact",
    "add-loc-telephone",
    "add-loc-email",
  ];

  let config = null;
  let dismissWithoutSave = false;

  function csrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  }

  function modalEl() {
    return document.getElementById("AddLocationModal");
  }

  function getBusinessId() {
    if (config.getBusinessId) return String(config.getBusinessId() || "");
    if (config.businessId) return String(config.businessId);
    return "";
  }

  function getLocationsMap() {
    if (config.getLocationsMap) return config.getLocationsMap() || {};
    return config.locationsMap || {};
  }

  function setLocationsMap(map) {
    if (config.locationsMap !== undefined) config.locationsMap = map;
  }

  function clearErrors() {
    const box = document.getElementById("add-location-errors");
    if (!box) return;
    box.classList.add("d-none");
    box.innerHTML = "";
  }

  function showErrors(errors) {
    const box = document.getElementById("add-location-errors");
    if (!box) return;
    const messages = [];
    if (errors && typeof errors === "object") {
      Object.values(errors).forEach((val) => {
        if (Array.isArray(val)) val.forEach((m) => messages.push(String(m)));
        else if (val) messages.push(String(val));
      });
    }
    if (!messages.length) {
      messages.push("Could not save location. Please check the fields and try again.");
    }
    box.innerHTML = messages.map((m) => `<div>${m}</div>`).join("");
    box.classList.remove("d-none");
  }

  function fieldValue(id) {
    return document.getElementById(id)?.value || "";
  }

  function setFieldValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value || "";
  }

  function resetForm() {
    FIELD_IDS.forEach((id) => setFieldValue(id, ""));
    setFieldValue("add-loc-id", "");
    const copySel = document.getElementById("add-loc-copy-contact");
    if (copySel) copySel.value = "";
    clearErrors();
    updateModalMode(false, false);
    const addressInput = document.getElementById("add-loc-address");
    if (addressInput) {
      delete addressInput.dataset.placesVisibleAttached;
    }
  }

  function updateModalMode(isEdit, isArchived) {
    const title = document.getElementById("AddLocationModalLabel");
    const deleteBtn = document.getElementById("add-location-delete");
    const unarchiveBtn = document.getElementById("add-location-unarchive");
    const archivedNotice = document.getElementById("add-location-archived-notice");
    if (title) title.textContent = isEdit ? "Edit training location" : "Add training location";
    if (deleteBtn) deleteBtn.classList.toggle("d-none", !isEdit || isArchived);
    if (unarchiveBtn) unarchiveBtn.classList.toggle("d-none", !isEdit || !isArchived);
    if (archivedNotice) archivedNotice.classList.toggle("d-none", !isEdit || !isArchived);
  }

  function rebuildContactCopyOptions(excludeId) {
    const sel = document.getElementById("add-loc-copy-contact");
    if (!sel) return;

    const bizId = getBusinessId();
    const prev = sel.value;

    sel.innerHTML = "";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "— Select existing contact —";
    sel.appendChild(blank);

    const items = Object.entries(getLocationsMap())
      .filter(([id, loc]) => String(loc.business_id) === bizId && String(id) !== String(excludeId || ""))
      .sort((a, b) => (a[1].name || "").localeCompare(b[1].name || "", undefined, { sensitivity: "base" }));

    for (const [id, loc] of items) {
      const o = document.createElement("option");
      o.value = id;
      const town = loc.town ? ` — ${loc.town}` : "";
      const contactLabel = loc.contact_name ? ` (${loc.contact_name})` : " (no contact set)";
      o.textContent = `${loc.name || "Location"}${town}${contactLabel}`;
      o.dataset.name = loc.contact_name || "";
      o.dataset.phone = loc.telephone || "";
      o.dataset.email = loc.email || "";
      sel.appendChild(o);
    }

    if (prev && Array.from(sel.options).some((o) => o.value === prev)) {
      sel.value = prev;
    }
  }

  function applyContactFromCopy() {
    const sel = document.getElementById("add-loc-copy-contact");
    if (!sel || !sel.value) return;
    const opt = sel.options[sel.selectedIndex];
    if (!opt || !opt.dataset) return;
    setFieldValue("add-loc-contact", opt.dataset.name);
    setFieldValue("add-loc-telephone", opt.dataset.phone);
    setFieldValue("add-loc-email", opt.dataset.email);
  }

  function initPlaces() {
    const el = modalEl();
    let addressInput = document.getElementById("add-loc-address");
    if (!addressInput || !el || !el.classList.contains("show")) return;
    if (!window.TrainingPlaces) return;
    if (!(window.google && google.maps && google.maps.places)) {
      document.addEventListener("gmaps:ready", initPlaces, { once: true });
      return;
    }
    if (addressInput.dataset.placesVisibleAttached === "1") return;

    const fieldMap = {
      addressLine: addressInput,
      town: "#add-loc-town",
      postcode: "#add-loc-postcode",
      propertyName: "#add-loc-property-name",
    };
    const reinit = addressInput.dataset.placesAttached === "1";
    window.TrainingPlaces.attach(addressInput, fieldMap, { reinit });
    addressInput = document.getElementById("add-loc-address");
    if (addressInput) addressInput.dataset.placesVisibleAttached = "1";
  }

  function fillFormFromLocation(loc) {
    setFieldValue("add-loc-id", loc.id || "");
    setFieldValue("add-loc-name", loc.name);
    setFieldValue("add-loc-property-name", loc.property_name);
    setFieldValue("add-loc-address", loc.address_line);
    setFieldValue("add-loc-town", loc.town);
    setFieldValue("add-loc-postcode", loc.postcode);
    setFieldValue("add-loc-contact", loc.contact_name);
    setFieldValue("add-loc-telephone", loc.telephone);
    setFieldValue("add-loc-email", loc.email);
  }

  function buildFormData() {
    const body = new FormData();
    body.append("business_id", getBusinessId());
    body.append("name", fieldValue("add-loc-name"));
    body.append("property_name", fieldValue("add-loc-property-name"));
    body.append("address_line", fieldValue("add-loc-address"));
    body.append("town", fieldValue("add-loc-town"));
    body.append("postcode", fieldValue("add-loc-postcode"));
    body.append("contact_name", fieldValue("add-loc-contact"));
    body.append("telephone", fieldValue("add-loc-telephone"));
    body.append("email", fieldValue("add-loc-email"));
    return body;
  }

  function showModal() {
    dismissWithoutSave = true;
    const el = modalEl();
    if (!el) return;
    bootstrap.Modal.getOrCreateInstance(el).show();
  }

  function hideModal() {
    dismissWithoutSave = false;
    const el = modalEl();
    if (!el) return;
    bootstrap.Modal.getInstance(el)?.hide();
  }

  function openAdd() {
    const bizId = getBusinessId();
    if (!bizId || bizId === "__add_business__") {
      alert("Please select a business first.");
      if (config.onCancelAdd) config.onCancelAdd();
      return;
    }
    resetForm();
    rebuildContactCopyOptions();
    updateModalMode(false, false);
    showModal();
  }

  function openEdit(locationId) {
    const bizId = getBusinessId();
    if (!bizId) return;

    const map = getLocationsMap();
    const loc = map[String(locationId)];
    if (!loc) return;

    resetForm();
    fillFormFromLocation({ ...loc, id: String(locationId) });
    rebuildContactCopyOptions(locationId);
    updateModalMode(true, loc.is_active === false);
    showModal();
  }

  async function saveLocation() {
    const bizId = getBusinessId();
    if (!bizId) {
      showErrors({ business_id: ["Business is required."] });
      return;
    }

    const locationId = fieldValue("add-loc-id");
    const isEdit = Boolean(locationId);
    const url = isEdit
      ? config.updateUrlTemplate.replace("{id}", encodeURIComponent(locationId))
      : config.createUrl;

    const saveBtn = document.getElementById("add-location-save");
    if (saveBtn) saveBtn.disabled = true;

    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: buildFormData(),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        showErrors(data.errors || {});
        return;
      }

      const map = getLocationsMap();
      map[data.location.id] = data.location;
      setLocationsMap(map);

      hideModal();
      if (config.onSaved) config.onSaved(data.location, isEdit);
    } catch (err) {
      console.error(err);
      showErrors({});
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  async function deleteLocation() {
    const locationId = fieldValue("add-loc-id");
    if (!locationId) return;

    const msg =
      "If this location has NO bookings, it will be permanently deleted.\n\n" +
      "If it HAS been used for bookings, it will be archived instead (so history is preserved).\n\n" +
      "Proceed?";
    const ok = window.confirmAction
      ? await window.confirmAction(msg.replace(/\n+/g, " "), { confirmLabel: "Delete / Archive" })
      : window.confirm(msg);
    if (!ok) return;

    const deleteBtn = document.getElementById("add-location-delete");
    if (deleteBtn) deleteBtn.disabled = true;

    try {
      const url = config.deleteUrlTemplate.replace("{id}", encodeURIComponent(locationId));
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        showErrors(data.errors || { _: ["Could not delete location."] });
        return;
      }

      const map = getLocationsMap();
      if (data.deleted) {
        delete map[String(locationId)];
      } else if (data.location) {
        map[data.location.id] = data.location;
      }
      setLocationsMap(map);

      hideModal();
      if (config.onDeleted) config.onDeleted(data, locationId);
    } catch (err) {
      console.error(err);
      showErrors({});
    } finally {
      if (deleteBtn) deleteBtn.disabled = false;
    }
  }

  async function unarchiveLocation() {
    const locationId = fieldValue("add-loc-id");
    if (!locationId || !config.unarchiveUrlTemplate) return;

    const msg = "Restore this location so it can be used for new bookings again?";
    if (!window.confirm(msg)) return;

    const unarchiveBtn = document.getElementById("add-location-unarchive");
    if (unarchiveBtn) unarchiveBtn.disabled = true;

    try {
      const url = config.unarchiveUrlTemplate.replace("{id}", encodeURIComponent(locationId));
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        showErrors(data.errors || { _: ["Could not restore location."] });
        return;
      }

      const map = getLocationsMap();
      if (data.location) {
        map[data.location.id] = data.location;
      }
      setLocationsMap(map);

      hideModal();
      if (config.onUnarchived) config.onUnarchived(data, locationId);
    } catch (err) {
      console.error(err);
      showErrors({});
    } finally {
      if (unarchiveBtn) unarchiveBtn.disabled = false;
    }
  }

  function bindEvents() {
    const el = modalEl();
    if (!el || el.dataset.adminLocationModalBound === "1") return;
    el.dataset.adminLocationModalBound = "1";

    el.addEventListener("shown.bs.modal", initPlaces);
    el.addEventListener("hidden.bs.modal", () => {
      if (dismissWithoutSave && config.onCancelAdd) config.onCancelAdd();
      dismissWithoutSave = true;
    });

    document.getElementById("add-location-save")?.addEventListener("click", saveLocation);
    document.getElementById("add-location-delete")?.addEventListener("click", deleteLocation);
    document.getElementById("add-location-unarchive")?.addEventListener("click", unarchiveLocation);
    document.getElementById("add-loc-copy-contact")?.addEventListener("change", applyContactFromCopy);
  }

  window.AdminLocationModal = {
    init(options) {
      config = {
        createUrl: options.createUrl,
        updateUrlTemplate: options.updateUrlTemplate,
        deleteUrlTemplate: options.deleteUrlTemplate,
        unarchiveUrlTemplate: options.unarchiveUrlTemplate || null,
        businessId: options.businessId || null,
        getBusinessId: options.getBusinessId || null,
        locationsMap: options.locationsMap || null,
        getLocationsMap: options.getLocationsMap || null,
        onSaved: options.onSaved || null,
        onDeleted: options.onDeleted || null,
        onUnarchived: options.onUnarchived || null,
        onCancelAdd: options.onCancelAdd || null,
      };
      bindEvents();
    },
    openAdd,
    openEdit,
    resetForm,
    rebuildContactCopyOptions,
  };
})();
