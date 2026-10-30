document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  const input = button.closest(".password-field").querySelector("input");
  const showLabel = button.dataset.labelShow || "Show password";
  const hideLabel = button.dataset.labelHide || "Hide password";

  button.addEventListener("click", () => {
    const show = input.type === "password";

    input.type = show ? "text" : "password";
    button.setAttribute("aria-pressed", String(show));
    button.setAttribute("aria-label", show ? hideLabel : showLabel);
  });
});