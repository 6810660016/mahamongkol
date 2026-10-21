document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.querySelector('[data-login-form]');
  if (!loginForm) return;

  loginForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const email = loginForm.querySelector('[name="email"]');
    const password = loginForm.querySelector('[name="password"]');
    const emailError = loginForm.querySelector('[data-email-error]');
    const passwordError = loginForm.querySelector('[data-password-error]');
    emailError.textContent = '';
    passwordError.textContent = '';

    let valid = true;
    if (!email.value.trim() || !email.validity.valid) {
      emailError.textContent = 'Please enter a valid email address';
      valid = false;
    }
    if (password.value.trim().length < 6) {
      passwordError.textContent = 'Password must be at least 6 characters';
      valid = false;
    }
    if (valid) window.location.href = '/home/';
  });
});
