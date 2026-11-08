document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('.booking-form');
  if (!form) return;

  const dateInput = form.querySelector('input[name="date"]');
  const guestsSelect = form.querySelector('select[name="guests"]');
  const timeSelect = form.querySelector('select[name="time"]');
  const buttons = form.querySelector('[data-slot-buttons]');
  const note = form.querySelector('[data-slot-note]');
  if (dateInput && !dateInput.value) {
    const today = new Date();
    dateInput.value = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  }

  const radios = () => [...form.querySelectorAll('input[name="time-choice"]')];
  const sync = (value) => {
    if (timeSelect) timeSelect.value = value;
    radios().forEach((radio) => { radio.checked = radio.value === value; });
  };
  form.addEventListener('change', (event) => {
    if (event.target.name === 'time-choice') sync(event.target.value);
    if (event.target === timeSelect) sync(timeSelect.value);
  });

  const labels = { full: 'เต็ม', past: 'ผ่านไปแล้ว', too_large: 'โต๊ะไม่พอสำหรับจำนวนคน' };
  const render = (slots) => {
    const previous = timeSelect ? timeSelect.value : '';
    timeSelect.replaceChildren();
    buttons.replaceChildren();
    slots.forEach((slot) => {
      const open = slot.state === 'open';
      const option = document.createElement('option');
      option.value = slot.value;
      option.disabled = !open;
      option.textContent = open ? slot.value : `${slot.value} · ${labels[slot.state]}`;
      timeSelect.append(option);

      const label = document.createElement('label');
      if (!open) label.className = 'is-unavailable';
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'time-choice';
      radio.value = slot.value;
      radio.disabled = !open;
      const text = document.createElement('span');
      text.textContent = slot.value;
      if (!open) {
        const small = document.createElement('small');
        small.textContent = labels[slot.state];
        text.append(' ', small);
      }
      label.append(radio, text);
      buttons.append(label);
    });
    const open = slots.filter((slot) => slot.state === 'open');
    const keep = open.find((slot) => slot.value === previous) || open[0];
    if (keep) sync(keep.value);
    note.textContent = open.length ? '' : 'ไม่มีเวลาว่างในวันนี้ กรุณาเลือกวันอื่น';
  };

  let request = 0;
  const refresh = async () => {
    if (!form.dataset.slotsUrl || !dateInput.value || !window.fetch) return;
    const id = ++request;
    const query = new URLSearchParams({ date: dateInput.value, guests: guestsSelect ? guestsSelect.value : '' });
    try {
      const response = await fetch(`${form.dataset.slotsUrl}?${query}`, { credentials: 'same-origin' });
      if (!response.ok || id !== request) return;
      render((await response.json()).slots);
    } catch (error) {
      /* keep the server-rendered times if the request fails */
    }
  };
  [dateInput, guestsSelect].forEach((input) => input && input.addEventListener('change', refresh));

  const first = radios().find((radio) => !radio.disabled);
  if (first && timeSelect && !timeSelect.value) sync(first.value);
  else if (timeSelect) sync(timeSelect.value);
  refresh();
});
