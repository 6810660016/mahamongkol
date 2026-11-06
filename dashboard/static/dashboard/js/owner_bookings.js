(() => {
  "use strict";
  const dateInput = document.querySelector("[data-booking-date]");
  if (!dateInput) return;
  const selectedDate = dateInput.value;
  const goToDate = (value) => { if (!value || value === selectedDate) return; const url = new URL(window.location.href); url.searchParams.set("date", value); window.location.assign(url); };
  const bookings = JSON.parse(document.getElementById("bookings-data").textContent);
  let filter = "all";
  const search = document.querySelector("[data-booking-search]");
  const groups = document.querySelector("[data-booking-groups]");
  const empty = document.querySelector("[data-booking-empty]");
  const dialog = document.querySelector("[data-booking-dialog]");
  const detail = document.querySelector("[data-booking-detail]");
  const calendarDays = document.querySelector("[data-calendar-days]");
  const [initialYear, initialMonth] = selectedDate.split("-").map(Number);
  let calendarYear = initialYear;
  let calendarMonth = initialMonth - 1;
  const cancelForm = document.querySelector("[data-cancel-form]");
  const element = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  function renderCalendar() {
    const monthStart = new Date(calendarYear, calendarMonth, 1);
    document.querySelector("[data-calendar-month]").textContent = monthStart.toLocaleDateString("en", { month: "long", year: "numeric" });
    const cells = Array.from({ length: monthStart.getDay() }, () => element("span", "booking-calendar__blank"));
    const daysInMonth = new Date(calendarYear, calendarMonth + 1, 0).getDate();
    for (let day = 1; day <= daysInMonth; day += 1) {
      const value = `${calendarYear}-${String(calendarMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const button = element("button", value === dateInput.value ? "is-selected" : "", String(day));
      button.type = "button";
      button.setAttribute("aria-label", new Date(calendarYear, calendarMonth, day).toLocaleDateString("en", { dateStyle: "full" }));
      if (value === dateInput.value) button.setAttribute("aria-current", "date");
      button.addEventListener("click", () => goToDate(value));
      cells.push(button);
    }
    calendarDays.replaceChildren(...cells);
  }
  function showDetails(booking) {
    const fields = [["Booking", booking.id], ["Guest", booking.name], ["Date", selectedDate], ["Time", booking.time], ["Table", booking.table], ["Party", `${booking.party} guests`], ["Status", booking.status === "confirmed" ? "Confirmed" : "Cancelled"]];
    detail.replaceChildren(...fields.map(([name, value]) => { const row = document.createElement("div"); row.append(element("dt", "", name), element("dd", "", value)); return row; }));
    cancelForm.action = booking.cancelUrl;
    cancelForm.hidden = booking.status !== "confirmed";
    dialog.showModal();
  }
  function render() {
    renderCalendar();
    const onDate = bookings;
    const term = search.value.trim().toLowerCase();
    const visible = onDate.filter((item) => (filter === "all" || item.status === filter) && `${item.name} ${item.id} ${item.table}`.toLowerCase().includes(term));
    document.querySelector("[data-summary-total]").textContent = onDate.length;
    document.querySelector("[data-summary-guests]").textContent = onDate.filter((item) => item.status === "confirmed").reduce((sum, item) => sum + item.party, 0);
    document.querySelector("[data-summary-confirmed]").textContent = onDate.filter((item) => item.status === "confirmed").length;
    document.querySelector("[data-summary-cancelled]").textContent = onDate.filter((item) => item.status === "cancelled").length;
    document.querySelector("[data-selected-date]").textContent = selectedDate;
    const times = [...new Set(visible.map((item) => item.time))];
    groups.replaceChildren(...times.map((time) => {
      const section = element("section", "booking-group");
      section.append(element("h3", "", time));
      const wrap = element("div", "booking-table-wrap");
      const table = element("table", "booking-table");
      const head = document.createElement("thead");
      const heading = document.createElement("tr");
      ["Guest", "Booking", "Table", "Party", "Status", "Details"].forEach((label) => heading.append(element("th", "", label)));
      head.append(heading); table.append(head);
      const body = document.createElement("tbody");
      visible.filter((item) => item.time === time).forEach((item) => {
        const row = document.createElement("tr");
        row.append(element("td", "", item.name), element("td", "", item.id), element("td", "", item.table), element("td", "", `${item.party} guests`));
        const status = document.createElement("td");
        status.append(element("span", `booking-status${item.status === "cancelled" ? " booking-status--cancelled" : ""}`, item.status === "cancelled" ? "Cancelled" : "Confirmed"));
        const action = document.createElement("td");
        const button = element("button", "booking-details-button", "↗"); button.type = "button"; button.setAttribute("aria-label", `View ${item.name} booking details`); button.addEventListener("click", () => showDetails(item)); action.append(button);
        row.append(status, action); body.append(row);
      });
      table.append(body); wrap.append(table); section.append(wrap); return section;
    }));
    empty.hidden = visible.length > 0;
  }
  dateInput.addEventListener("change", () => goToDate(dateInput.value)); search.addEventListener("input", render);
  cancelForm.addEventListener("submit", (event) => { if (!window.confirm("ยืนยันการยกเลิกการจองนี้?")) event.preventDefault(); });
  document.querySelector("[data-month-prev]").addEventListener("click", () => { const date = new Date(calendarYear, calendarMonth - 1, 1); calendarYear = date.getFullYear(); calendarMonth = date.getMonth(); renderCalendar(); });
  document.querySelector("[data-month-next]").addEventListener("click", () => { const date = new Date(calendarYear, calendarMonth + 1, 1); calendarYear = date.getFullYear(); calendarMonth = date.getMonth(); renderCalendar(); });
  document.querySelectorAll("[data-booking-filter]").forEach((button) => button.addEventListener("click", () => { filter = button.dataset.bookingFilter; document.querySelectorAll("[data-booking-filter]").forEach((item) => { item.classList.toggle("is-active", item === button); item.setAttribute("aria-pressed", item === button ? "true" : "false"); }); render(); }));
  document.querySelectorAll("[data-close-booking]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  render();
})();
