document.addEventListener('DOMContentLoaded', () => {
  const searchForm = document.querySelector('[data-search-form]');
  if (!searchForm) return;

  searchForm.addEventListener('submit', () => {
    const button = searchForm.querySelector('button[type="submit"]');
    if (button) button.textContent = 'Searching…';
    
  });
});

window.addEventListener('pageshow', () => {
  const searchForm = document.querySelector('[data-search-form]');
  if (!searchForm) return;

  const button = searchForm.querySelector('button[type="submit"]');

  if (button) {
    button.textContent = 'Search';
    button.disabled = false;
  }
});