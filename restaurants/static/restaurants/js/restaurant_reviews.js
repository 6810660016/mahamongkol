(() => {
  const section = document.querySelector('[data-reviews]');
  if (!section) return;
  const form = section.querySelector('[data-review-form]');
  const radios = [...form.querySelectorAll('input[name="rating"]')];
  const message = form.elements.message;
  const labels = ['', 'Poor', 'Fair', 'Good', 'Very good', 'Excellent'];
  const updateStars = (value) => {
    radios.forEach((radio) => radio.parentElement.classList.toggle('is-filled', Number(radio.value) <= value));
    section.querySelector('[data-rating-label]').textContent = value ? labels[value] : 'Select a rating';
  };
  radios.forEach((radio) => radio.addEventListener('change', () => updateStars(Number(radio.value))));
  message.addEventListener('input', () => { section.querySelector('[data-review-count]').textContent = message.value.length; });
  const status = section.querySelector('[data-review-status]');
  const show = (rating, text) => {
    const stars = section.querySelector('[data-review-stars]');
    stars.textContent = '★'.repeat(rating) + '☆'.repeat(5 - rating);
    stars.setAttribute('aria-label', `${rating} out of 5 stars`);
    section.querySelector('[data-review-text]').textContent = text || 'No written review provided.';
    section.querySelector('[data-review-empty]').hidden = true;
    section.querySelector('[data-review-entry]').hidden = false;
    form.querySelector('[type="submit"]').firstChild.textContent = 'Update review ';
  };
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    status.textContent = 'Saving…';
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not save your review.');
      show(data.rating, data.message);
      status.textContent = 'Review saved.';
    } catch (error) {
      status.textContent = error.message || 'Could not save your review.';
    }
  });
  section.querySelector('[data-edit-review]').addEventListener('click', () => {
    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    (form.querySelector('input[name="rating"]:checked') || radios[0]).focus({ preventScroll: true });
  });
})();
