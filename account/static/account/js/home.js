document.addEventListener('DOMContentLoaded', () => {
  const searchForm = document.querySelector('[data-search-form]');
  if (!searchForm) return;

  searchForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const input = searchForm.querySelector('input');
    input.focus();
    input.setAttribute('placeholder', input.value ? `Searching for “${input.value}”` : 'Try searching for “restaurants near me”');
  });
});
