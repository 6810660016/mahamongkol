(() => {
  "use strict";
  const form = document.querySelector("[data-store-detail-form]");
  if (!form) return;
  const list = form.querySelector("[data-slot-list]");
  const toast = document.querySelector("[data-store-toast]");
  let toastTimer;
  const announce = (message) => { toast.textContent = message; toast.classList.add("is-visible"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3500); };
  form.querySelectorAll("[data-image-input]").forEach((input) => {
    let previewUrl;
    input.addEventListener("change", () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      const image = input.closest(".store-upload").querySelector("img");
      const label = input.closest(".store-upload").querySelector("[data-image-label]");
      const file = input.files[0];
      if (!file) { image.hidden = true; label.hidden = false; return; }
      previewUrl = URL.createObjectURL(file);
      image.src = previewUrl;
      image.hidden = false;
      label.hidden = true;
    });
  });
  form.querySelector("[data-add-slot]").addEventListener("click", () => {
    const row = document.createElement("tr");
    row.innerHTML = '<td><input type="checkbox" checked aria-label="Slot available"></td><td><input type="time" value="14:00" aria-label="Slot time"></td><td><input type="number" value="4" min="1" max="100" aria-label="Tables"></td><td><button type="button" data-remove-slot aria-label="Remove slot">×</button></td>';
    list.append(row);
  });
  list.addEventListener("click", (event) => { const button = event.target.closest("[data-remove-slot]"); if (button) button.closest("tr").remove(); });
  form.addEventListener("submit", (event) => { event.preventDefault(); if (form.reportValidity()) announce("Preview updated on this page only. No store data was saved."); });
})();
