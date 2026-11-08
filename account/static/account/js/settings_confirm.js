// Ask for confirmation before the settings form is saved.
// Without JavaScript (or <dialog> support) the form still submits normally.
const form = document.getElementById("settings-form");
const dialog = document.getElementById("settings-confirm");

if (form && dialog && typeof dialog.showModal === "function") {
  const nameInput = form.querySelector('input[name="name"]');
  const nameLabel = dialog.querySelector("[data-confirm-name]");
  const confirmButton = dialog.querySelector("[data-confirm-ok]");
  let confirmed = false;

  form.addEventListener("submit", (event) => {
    if (confirmed) return;
    event.preventDefault();
    const name = nameInput.value.trim() || nameInput.placeholder;
    nameLabel.textContent = `“${name}”`;
    dialog.showModal();
    confirmButton.focus();
  });

  dialog.querySelector("[data-confirm-cancel]").addEventListener("click", () => {
    dialog.close();
  });

  confirmButton.addEventListener("click", () => {
    confirmed = true;
    confirmButton.disabled = true;
    dialog.close();
    form.requestSubmit();
  });
}
