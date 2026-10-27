(() => {
  "use strict";

  // Deliberately in-memory only. Refreshing this page restores the sample data.
  const sampleStores = [
    { id: "sample-bistro", name: "Sample Bistro", category: "Restaurant", price: "$$ · Mid-range", address: "48 Sukhumvit Road, Bangkok", hours: "Daily · 11:00 AM – 10:00 PM", image: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=900&q=85", description: "A sample listing for exploring the owner workspace and its store controls.", status: "published", isOpen: true, extras: [{ key: "Booking note", value: "Sample data only" }] },
    { id: "sample-cafe", name: "Demo Garden Café", category: "Café", price: "$ · Casual", address: "12 Garden Lane, Chiang Mai", hours: "Tue–Sun · 8:00 AM – 6:00 PM", image: "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?auto=format&fit=crop&w=900&q=85", description: "A fictional café card to preview how a second location appears.", status: "published", isOpen: false, extras: [] },
    { id: "sample-wellness", name: "Preview Wellness House", category: "Wellness", price: "$$$ · Premium", address: "7 Riverside Avenue, Bangkok", hours: "Daily · 10:00 AM – 8:00 PM", image: "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=900&q=85", description: "A draft example. Publishing here is only a visual prototype action.", status: "draft", isOpen: true, extras: [{ key: "Service type", value: "Preview treatment" }] },
  ];

  const grid = document.querySelector("[data-store-grid]");
  if (!grid) return;
  let stores = sampleStores;
  let activeFilter = "all";
  let editingId = null;
  let toastTimer;

  const dialog = document.querySelector("[data-store-dialog]");
  const form = document.querySelector("[data-store-form]");
  const extraList = document.querySelector("[data-extra-list]");
  const search = document.querySelector("[data-store-search]");
  const emptyState = document.querySelector("[data-empty-state]");
  const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const formatStatus = (store) => store.status === "draft" ? "Draft" : store.isOpen ? "Open" : "Closed";
  const notify = (message) => {
    const toast = document.querySelector("[data-owner-toast]");
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 3200);
  };

  function render() {
    const query = (search.value || "").trim().toLowerCase();
    const visible = stores.filter((store) => {
      const matchesFilter = activeFilter === "all" || (activeFilter === "published" && store.status === "published" && store.isOpen) || (activeFilter === "draft" && store.status === "draft") || (activeFilter === "closed" && store.status === "published" && !store.isOpen);
      const matchesQuery = `${store.name} ${store.category} ${store.address}`.toLowerCase().includes(query);
      return matchesFilter && matchesQuery;
    });
    grid.replaceChildren(...visible.map((store) => {
      const card = document.createElement("article");
      card.className = `owner-store-card${store.status === "published" && !store.isOpen ? " is-closed" : ""}`;
      const statusClass = store.status === "draft" ? "draft" : store.isOpen ? "open" : "closed";
      const extra = store.extras?.[0] ? `<p class="owner-store-card__detail-line">${escapeHTML(store.extras[0].key)}: ${escapeHTML(store.extras[0].value)}</p>` : "";
      card.innerHTML = `
        <div class="owner-store-card__image">
          <span class="owner-store-card__sample">SAMPLE LISTING</span>
          <span class="owner-store-card__status owner-store-card__status--${statusClass}">${formatStatus(store)}</span>
        </div>
        <div class="owner-store-card__body">
          <div class="owner-store-card__meta"><span class="owner-store-card__category">${escapeHTML(store.category)}</span><span>${escapeHTML(store.price || "Price not set")}</span></div>
          <h3 title="${escapeHTML(store.name)}">${escapeHTML(store.name)}</h3>
          <p class="owner-store-card__address">⌖ ${escapeHTML(store.address || "Address not provided")}</p>
          <p class="owner-store-card__description">${escapeHTML(store.description || "No description added.")}</p>${extra}
          <div class="owner-store-card__actions">
            ${store.status === "draft" ? '<button type="button" data-action="publish">Publish preview</button>' : `<button type="button" data-action="toggle">${store.isOpen ? "Close store" : "Open store"}</button>`}
            <button type="button" data-action="edit">Edit</button><button type="button" data-action="delete">Delete</button>
          </div>
        </div>`;
      if (store.image) {
        try {
          const imageUrl = new URL(store.image, window.location.href);
          if (imageUrl.protocol === "https:" || imageUrl.protocol === "http:") {
            card.querySelector(".owner-store-card__image").style.backgroundImage = `url(${JSON.stringify(imageUrl.href)})`;
          }
        } catch (_) { /* Ignore invalid preview image URLs. */ }
      }
      card.querySelector("[data-action='publish']")?.addEventListener("click", () => updateStore(store.id, { status: "published" }, "Published in this preview only; the team’s approval policy is still undecided."));
      card.querySelector("[data-action='toggle']")?.addEventListener("click", () => updateStore(store.id, { isOpen: !store.isOpen }, `Store marked ${store.isOpen ? "closed" : "open"} in this preview only.`));
      card.querySelector("[data-action='edit']").addEventListener("click", () => openEditor(store));
      card.querySelector("[data-action='delete']").addEventListener("click", () => {
        if (!window.confirm(`Remove “${store.name}” from this temporary preview?`)) return;
        stores = stores.filter((item) => item.id !== store.id);
        render();
        notify("Removed from this preview only. No saved store data was deleted.");
      });
      return card;
    }));
    emptyState.hidden = visible.length > 0;
    const published = stores.filter((item) => item.status === "published").length;
    const drafts = stores.filter((item) => item.status === "draft").length;
    document.querySelector("[data-stat-total]").textContent = stores.length;
    document.querySelector("[data-stat-published]").textContent = published;
    document.querySelector("[data-stat-drafts]").textContent = drafts;
    document.querySelector("[data-nav-store-count]").textContent = stores.length;
    document.querySelector("[data-heading-store-count]").textContent = stores.length;
  }

  function updateStore(id, values, message) {
    stores = stores.map((store) => store.id === id ? { ...store, ...values } : store);
    render();
    notify(message);
  }

  function addExtraRow(key = "", value = "") {
    const row = document.createElement("div");
    row.className = "owner-extra-row";
    row.innerHTML = `<input aria-label="Detail name" placeholder="e.g. Parking" maxlength="60" value="${escapeHTML(key)}"><input aria-label="Detail value" placeholder="e.g. Available on site" maxlength="160" value="${escapeHTML(value)}"><button type="button" aria-label="Remove detail">×</button>`;
    row.querySelector("button").addEventListener("click", () => row.remove());
    extraList.append(row);
  }

  function resetForm() {
    form.reset();
    extraList.replaceChildren();
    editingId = null;
    document.querySelector("[data-dialog-title]").textContent = "Add a store";
    form.querySelector("[type='submit']").innerHTML = "<span aria-hidden='true'>＋</span> Save as draft";
  }

  function openEditor(store = null) {
    resetForm();
    if (store) {
      editingId = store.id;
      document.querySelector("[data-dialog-title]").textContent = "Edit store";
      form.elements.name.value = store.name;
      form.elements.category.value = store.category;
      form.elements.price.value = store.price || "";
      form.elements.address.value = store.address || "";
      form.elements.hours.value = store.hours || "";
      form.elements.image.value = store.image || "";
      form.elements.description.value = store.description || "";
      (store.extras || []).forEach((extra) => addExtraRow(extra.key, extra.value));
      form.querySelector("[type='submit']").innerHTML = "<span aria-hidden='true'>✓</span> Save preview changes";
    }
    dialog.showModal();
    form.elements.name.focus();
  }

  document.querySelectorAll("[data-open-store]").forEach((button) => button.addEventListener("click", () => openEditor()));
  document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  document.querySelector("[data-add-extra]").addEventListener("click", () => addExtraRow());
  document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
    activeFilter = button.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
    render();
  }));
  search.addEventListener("input", render);
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener("close", resetForm);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const extras = [...extraList.querySelectorAll(".owner-extra-row")].map((row) => {
      const inputs = row.querySelectorAll("input");
      return { key: inputs[0].value.trim(), value: inputs[1].value.trim() };
    }).filter((item) => item.key || item.value);
    const values = { name: data.get("name").trim(), category: data.get("category"), price: data.get("price"), address: data.get("address").trim(), hours: data.get("hours").trim(), image: data.get("image").trim(), description: data.get("description").trim(), extras };
    if (editingId) {
      stores = stores.map((store) => store.id === editingId ? { ...store, ...values } : store);
      notify("Preview changes updated. They are not saved to the database.");
    } else {
      stores = [{ id: `preview-${Date.now()}-${Math.random().toString(16).slice(2)}`, ...values, status: "draft", isOpen: true }, ...stores];
      notify("Draft added to this preview only.");
    }
    dialog.close();
    render();
  });

  render();
})();
