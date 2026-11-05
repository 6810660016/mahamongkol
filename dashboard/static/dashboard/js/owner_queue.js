(() => {
  "use strict";

  // The owner dashboard is a mockup. Nothing here reads or writes real bookings.
  const root = document.querySelector(".queue-app");
  if (!root) return;
  const $ = (selector) => document.querySelector(selector);
  const ago = (minutes) => Date.now() - minutes * 60000;
  let nextNumber = 13;
  let paused = false;
  let current = { number: 8, source: "Booking", party: 4, name: "", joinedAt: ago(25) };
  let waiting = [
    { number: 9, source: "Booking", party: 2, name: "", joinedAt: ago(20) },
    { number: 10, source: "Walk-in", party: 4, name: "", joinedAt: ago(15) },
    { number: 11, source: "Booking", party: 3, name: "", joinedAt: ago(10) },
    { number: 12, source: "Walk-in", party: 5, name: "", joinedAt: ago(5) },
    { number: 13, source: "Booking", party: 2, name: "", joinedAt: ago(1) },
  ];
  let skipped = [{ number: 7, source: "Walk-in", party: 2, name: "", joinedAt: ago(30) }];
  let completed = 0;
  let toastTimer;
  const number = (entry) => `Q${String(entry.number).padStart(3, "0")}`;
  const partyText = (count) => `${count} ${count === 1 ? "guest" : "guests"}`;
  const waitingTime = (entry) => `${Math.max(0, Math.floor((Date.now() - entry.joinedAt) / 60000))} min`;

  function announce(message) {
    const toast = $("[data-toast]");
    toast.textContent = message;
    toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3500);
  }

  function makeElement(tag, className, content) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined) element.textContent = content;
    return element;
  }

  function advance() {
    current = waiting.shift() || null;
    if (current) current.priority = false;
  }

  function render() {
    $("[data-stat-waiting]").textContent = waiting.length;
    $("[data-stat-current]").textContent = current ? number(current) : "—";
    $("[data-stat-completed]").textContent = completed;
    $("[data-stat-skipped]").textContent = skipped.length;
    const averageWait = waiting.length ? Math.round(waiting.reduce((sum, entry) => sum + Math.max(0, Date.now() - entry.joinedAt), 0) / waiting.length / 60000) : 0;
    $("[data-stat-average]").textContent = `${averageWait} min`;
    $("[data-waiting-count]").textContent = `${waiting.length} waiting`;
    $("[data-skipped-count]").textContent = skipped.length;
    $("[data-current-number]").textContent = current ? number(current) : "—";
    $("[data-current-detail]").textContent = current ? partyText(current.party) : "No queue being served";
    $("[data-current-source]").textContent = current ? `${current.source}${current.name ? ` · ${current.name}` : ""}` : "Call the next party when ready";
    $("[data-current-badge]").textContent = current ? "● NOW SERVING" : "● READY TO CALL";
    $("[data-call-again]").disabled = !current;
    $("[data-complete]").disabled = !current;
    $("[data-skip]").hidden = !current;
    $("[data-call-next]").hidden = Boolean(current);
    $("[data-call-next]").disabled = !waiting.length;

    const rows = waiting.map((entry) => {
      const row = document.createElement("tr");
      row.append(makeElement("td", "queue-table__number", number(entry)));
      row.append(makeElement("td", "", entry.source));
      row.append(makeElement("td", "", partyText(entry.party)));
      row.append(makeElement("td", "", waitingTime(entry)));
      const status = document.createElement("td");
      status.append(makeElement("span", entry.priority ? "queue-status queue-status--priority" : "queue-status", entry.priority ? "Next · recalled" : "Waiting"));
      row.append(status);
      return row;
    });
    $("[data-waiting-list]").replaceChildren(...rows);
    $("[data-waiting-empty]").hidden = waiting.length > 0;

    const skippedRows = skipped.map((entry) => {
      const row = makeElement("div", "queue-skipped__item");
      const details = document.createElement("span");
      details.append(makeElement("strong", "", number(entry)), makeElement("small", "", `${entry.source} · ${partyText(entry.party)}`));
      const button = makeElement("button", "", "Recall next ↗");
      button.type = "button";
      button.setAttribute("aria-label", `Recall ${number(entry)} as the next queue`);
      button.addEventListener("click", () => {
        skipped = skipped.filter((item) => item.number !== entry.number);
        entry.priority = true;
        waiting.unshift(entry);
        if (!current) advance();
        render();
        announce(current && current.number === entry.number ? `${number(entry)} is now being served in this preview.` : `${number(entry)} will be called after the current queue.`);
      });
      row.append(details, button);
      return row;
    });
    $("[data-skipped-list]").replaceChildren(...skippedRows);
    $("[data-skipped-empty]").hidden = skipped.length > 0;
    $("[data-toggle-pause]").textContent = paused ? "▶  Resume new queues" : "Ⅱ  Pause new queues";
    document.querySelectorAll("[data-open-add]").forEach((button) => { button.disabled = paused; });
  }

  $("[data-call-again]").addEventListener("click", () => { if (current) announce(`Calling ${number(current)} again in this preview.`); });
  $("[data-complete]").addEventListener("click", () => {
    if (!current) return;
    const previous = number(current);
    completed += 1;
    advance();
    render();
    announce(`${previous} completed. ${current ? `${number(current)} is now being served.` : "No queues are waiting."}`);
  });
  $("[data-skip]").addEventListener("click", () => {
    if (!current) return;
    const previous = number(current);
    skipped.push(current);
    advance();
    render();
    announce(`${previous} skipped. ${current ? `${number(current)} is now being served.` : "No queues are waiting."}`);
  });
  $("[data-call-next]").addEventListener("click", () => { if (!current && waiting.length) { advance(); render(); announce(`${number(current)} is now being served.`); } });
  $("[data-toggle-pause]").addEventListener("click", () => { paused = !paused; render(); announce(paused ? "New sample queues are paused." : "New sample queues are open."); });

  const dialog = $("[data-add-dialog]");
  const form = $("[data-add-form]");
  document.querySelectorAll("[data-open-add]").forEach((button) => button.addEventListener("click", () => { if (!paused) dialog.showModal(); }));
  document.querySelectorAll("[data-close-add]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("close", () => form.reset());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (paused || !form.reportValidity()) return;
    const fields = new FormData(form);
    const entry = { number: ++nextNumber, source: fields.get("source"), name: fields.get("name").trim(), party: Number(fields.get("party")), joinedAt: Date.now() };
    waiting.push(entry);
    dialog.close();
    render();
    announce(`${number(entry)} added to the preview as a ${entry.source.toLowerCase()} queue.`);
  });
  render();
  setInterval(render, 60000);
})();
