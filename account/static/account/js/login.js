document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  const input = button.closest(".password-field").querySelector("input");

  button.addEventListener("click", () => {
    const show = input.type === "password";

    input.type = show ? "text" : "password";
    button.setAttribute("aria-pressed", String(show));
    button.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
});