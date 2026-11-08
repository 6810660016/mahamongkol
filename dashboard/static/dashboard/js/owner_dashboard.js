(() => {
  "use strict";

  const serviceModeLabels = { both: "Bookings + queue", booking: "Bookings only", queue: "Queue only" };

  // Stores come from the server (json_script in the template).
  const stores = JSON.parse(document.getElementById("stores-data").textContent);

  const grid = document.querySelector("[data-store-grid]");
  if (!grid) return;
  let activeFilter = "all";
  let toastTimer;

  const dialog = document.querySelector("[data-store-dialog]");
  const form = document.querySelector("[data-store-form]");
  const extraList = document.querySelector("[data-extra-list]");
  const search = document.querySelector("[data-store-search]");
  const emptyState = document.querySelector("[data-empty-state]");

  const createUrl = form.getAttribute("action");
  const csrfToken = form.elements.csrfmiddlewaretoken.value;

  // Submit a hidden POST form (used by publish / open-close / delete).
  function postAction(url, fields = {}) {
    const f = document.createElement("form");
    f.method = "post";
    f.action = url;
    Object.entries({ csrfmiddlewaretoken: csrfToken, ...fields }).forEach(([name, value]) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = value;
      f.append(input);
    });
    document.body.append(f);
    f.submit();
  }
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
          <span class="owner-store-card__status owner-store-card__status--${statusClass}">${formatStatus(store)}</span>
        </div>
        <div class="owner-store-card__body">
          <div class="owner-store-card__meta"><span class="owner-store-card__category">${escapeHTML(store.category)}</span><span>${escapeHTML(store.price || "Price not set")}</span><span>${escapeHTML(serviceModeLabels[store.serviceMode] || serviceModeLabels.both)}</span></div>
          <h3 title="${escapeHTML(store.name)}">${escapeHTML(store.name)}</h3>
          <p class="owner-store-card__address">⌖ ${escapeHTML(store.address || "Address not provided")}</p>
          <p class="owner-store-card__description">${escapeHTML(store.description || "No description added.")}</p>${extra}
          <div class="owner-store-card__actions">
            ${store.status === "draft" ? '<button type="button" data-action="publish">Publish</button>' : `<button type="button" data-action="toggle">${store.isOpen ? "Close store" : "Open store"}</button>`}
            <a data-action="edit" href="${escapeHTML(store.urls.details)}">Edit</a><button type="button" data-action="delete">Delete</button>
          </div>
        </div>`;
      if (store.image) {
        try {
          const imageUrl = new URL(store.image, window.location.href);
          if (imageUrl.protocol === "https:" || imageUrl.protocol === "http:") {
            card.querySelector(".owner-store-card__image").style.backgroundImage = `url(${JSON.stringify(imageUrl.href)})`;
          }
        } catch (_) { /* Ignore invalid image URLs. */ }
      }
      card.querySelector("[data-action='publish']")?.addEventListener("click", () =>
        postAction(store.urls.status, { status: "published" }));
      card.querySelector("[data-action='toggle']")?.addEventListener("click", () =>
        postAction(store.urls.status, { is_open: store.isOpen ? "0" : "1" }));
      card.querySelector("[data-action='delete']").addEventListener("click", () => {
        if (!window.confirm(`ลบร้าน “${store.name}” ?`)) return;
        postAction(store.urls.delete);
      });
      return card;
    }));
    emptyState.hidden = visible.length > 0;
    const published = stores.filter((item) => item.status === "published").length;
    const drafts = stores.filter((item) => item.status === "draft").length;
    document.querySelector("[data-stat-total]").textContent = stores.length;
    document.querySelector("[data-stat-published]").textContent = published;
    document.querySelector("[data-stat-drafts]").textContent = drafts;
    document.querySelector("[data-heading-store-count]").textContent = stores.length;
  }

  function addExtraRow(key = "", value = "") {
    const row = document.createElement("div");
    row.className = "owner-extra-row";
    row.innerHTML = `<input name="extra_key" aria-label="Detail name" placeholder="e.g. Parking" maxlength="60" value="${escapeHTML(key)}"><input name="extra_value" aria-label="Detail value" placeholder="e.g. Available on site" maxlength="160" value="${escapeHTML(value)}"><button type="button" aria-label="Remove detail">×</button>`;
    row.querySelector("button").addEventListener("click", () => row.remove());
    extraList.append(row);
  }

  function resetForm() {
    form.reset();
    form.action = createUrl;
    extraList.replaceChildren();
    document.querySelector("[data-dialog-title]").textContent = "Add a store";
    form.querySelector("[type='submit']").innerHTML = "<span aria-hidden='true'>＋</span> Save as draft";
  }

  // The dialog only creates a store. Editing an existing store happens on the Store Details page.
  function openCreateDialog() {
    resetForm();
    dialog.showModal();
    form.elements.name.focus();
  }

  document.querySelectorAll("[data-open-store]").forEach((button) => button.addEventListener("click", () => openCreateDialog()));
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
  const flash = [...document.querySelectorAll("[data-flash]")].map((el) => el.textContent.trim());
  if (flash.length) notify(flash.join(" · "));
  render();

  if (new URLSearchParams(window.location.search).get("add_store") === "1" && document.querySelector("[data-open-store]")) {
    openCreateDialog();
  }
})();