document.addEventListener('DOMContentLoaded', () => {
  const searchForm = document.querySelector('[data-search-form]');
  if (!searchForm) return;

  searchForm.addEventListener('submit', () => {
    const button = searchForm.querySelector('button[type="submit"]');
    if (button) button.textContent = 'Searching…';
  });
});
