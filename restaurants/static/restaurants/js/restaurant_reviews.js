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
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const rating = Number(form.elements.rating.value);
    const stars = section.querySelector('[data-review-stars]');
    stars.textContent = '★'.repeat(rating) + '☆'.repeat(5 - rating);
    stars.setAttribute('aria-label', `${rating} out of 5 stars`);
    section.querySelector('[data-review-text]').textContent = message.value.trim() || 'No written review provided.';
    section.querySelector('[data-review-empty]').hidden = true;
    section.querySelector('[data-review-entry]').hidden = false;
    section.querySelector('[data-review-status]').textContent = 'Preview review posted. It will reset when you refresh.';
    form.querySelector('[type="submit"]').firstChild.textContent = 'Update preview review ';
  });
  section.querySelector('[data-edit-review]').addEventListener('click', () => {
    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    (form.querySelector('input[name="rating"]:checked') || radios[0]).focus({ preventScroll: true });
  });
})();
