(() => {
  "use strict";

  // Owner queue page. All state lives on the server (queues app); this page
  // renders the latest snapshot and refreshes it every few seconds.
  const root = document.querySelector(".queue-app");
  if (!root) return;
  const $ = (selector) => document.querySelector(selector);
  const POLL_MS = 4000;
  let state = { queueEnabled: true, paused: false, current: null, waiting: [], skipped: [], completed: 0 };
  let toastTimer;
  let busy = false;
  const queueEnabled = () => state.queueEnabled !== false && root.dataset.queueEnabled !== "0";

  const number = (entry) => entry.code;
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

  async function request(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { "X-CSRFToken": root.dataset.csrf },
      ...options,
    });
    let data = {};
    try { data = await response.json(); } catch (error) { /* not JSON, e.g. a redirect to sign-in */ }
    if (!response.ok && !data.error) data.error = "Something went wrong. Please reload the page.";
    return data;
  }

  function apply(data) {
    if (data && Array.isArray(data.waiting)) state = data;
    render();
  }

  async function act(url, body, { silent = false } = {}) {
    if (busy) return;
    busy = true;
    try {
      const data = await request(url, { method: "POST", body: new URLSearchParams(body || {}) });
      apply(data);
      if (data.error) announce(data.error);
      else if (data.message && !silent) announce(data.message);
      return data;
    } catch (error) {
      announce("Could not reach the server. Try again.");
    } finally {
      busy = false;
    }
  }

  async function refresh() {
    if (busy || document.hidden || root.dataset.hasStore !== "1") return;
    try { apply(await request(root.dataset.urlData)); } catch (error) { /* keep the last snapshot */ }
  }

  function render() {
    const { current, waiting, skipped } = state;
    $("[data-stat-waiting]").textContent = waiting.length;
    $("[data-stat-current]").textContent = current ? number(current) : "—";
    $("[data-stat-completed]").textContent = state.completed;
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
      row.append(makeElement("td", "", `${entry.source}${entry.name ? ` · ${entry.name}` : ""}`));
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
      button.addEventListener("click", () => act(root.dataset.urlRecall.replace(/0\/recall\/$/, `${entry.id}/recall/`)));
      row.append(details, button);
      return row;
    });
    $("[data-skipped-list]").replaceChildren(...skippedRows);
    $("[data-skipped-empty]").hidden = skipped.length > 0;
    $("[data-toggle-pause]").textContent = state.paused ? "▶  Resume new queues" : "Ⅱ  Pause new queues";
    document.querySelectorAll("[data-open-add]").forEach((button) => { button.disabled = state.paused || !queueEnabled(); });
  }

  $("[data-call-again]").addEventListener("click", () => act(root.dataset.urlCallAgain));
  $("[data-complete]").addEventListener("click", () => act(root.dataset.urlComplete));
  $("[data-skip]").addEventListener("click", () => act(root.dataset.urlSkip));
  $("[data-call-next]").addEventListener("click", () => act(root.dataset.urlCallNext));
  $("[data-toggle-pause]").addEventListener("click", () => act(root.dataset.urlPause, { paused: state.paused ? "0" : "1" }));

  const dialog = $("[data-add-dialog]");
  const form = $("[data-add-form]");
  document.querySelectorAll("[data-open-add]").forEach((button) => button.addEventListener("click", async () => {
    if (state.paused || !queueEnabled()) return;
    dialog.showModal();
  }));
  document.querySelectorAll("[data-close-add]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("close", () => form.reset());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.paused || !queueEnabled() || !form.reportValidity()) return;
    const fields = new FormData(form);
    const body = { name: (fields.get("name") || "").trim(), party: fields.get("party") };
    const data = await act(root.dataset.urlAdd, body);
    if (data && !data.error) dialog.close();
  });

  render();
  refresh();
  setInterval(refresh, POLL_MS);
  setInterval(render, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();
