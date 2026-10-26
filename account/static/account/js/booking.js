document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('.booking-form');
  if (!form) return;

  const dateInput = form.querySelector('input[name="date"]');
  const timeSelect = form.querySelector('select[name="time"]');
  const timeRadios = form.querySelectorAll('input[name="time-choice"]');
  if (dateInput && !dateInput.value) {
    const today = new Date();
    dateInput.value = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  }
  timeRadios.forEach((radio) => {
    radio.addEventListener('change', () => {
      if (radio.checked && timeSelect) timeSelect.value = radio.value;
    });
  });
  if (timeSelect) {
    timeSelect.addEventListener('change', () => {
      const active = [...timeRadios].find((radio) => radio.value === timeSelect.value);
      if (active) active.checked = true;
    });
  }
});
