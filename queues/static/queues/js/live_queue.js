(() => {
  "use strict";

  // Live place-in-line cards on the customer's My Q page (refresh every 4 s).
  const root = document.querySelector("[data-live-queue]");
  if (!root) return;
  const list = root.querySelector("[data-live-queue-list]");
  const errorBox = root.querySelector("[data-live-queue-error]");
  const POLL_MS = 4000;

  const make = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  function describe(queue) {
    if (queue.status === "serving") return "It's your turn — please come to the host stand.";
    if (queue.status === "skipped") return "You were skipped. Please see the staff to be called again.";
    const ahead = queue.ahead === null ? 0 : queue.ahead;
    const serving = queue.nowServing ? `Now serving ${queue.nowServing}. ` : "";
    return `${serving}${ahead === 0 ? "You're next!" : `${ahead} ${ahead === 1 ? "party" : "parties"} ahead of you.`}`;
  }

  function badge(queue) {
    if (queue.status === "serving") return "YOUR TURN";
    if (queue.status === "skipped") return "SKIPPED";
    return queue.ahead === 0 ? "YOU'RE NEXT" : "WAITING";
  }

  function render(queues) {
    root.hidden = queues.length === 0;
    list.replaceChildren(...queues.map((queue) => {
      const card = make("article", `live-queue-card${queue.status === "serving" ? " live-queue-card--called" : ""}`);
      const info = make("div");
      info.append(
        make("p", "eyebrow", `${badge(queue)} · ${queue.party} ${queue.party === 1 ? "guest" : "guests"}`),
        make("h2", "", queue.restaurant),
        make("p", "", describe(queue)),
      );
      const number = make("div", "live-queue-card__number", queue.code);
      number.append(make("small", "", "YOUR NUMBER"));
      const actions = make("div", "live-queue-card__actions");
      const view = make("a", "", "View place");
      view.href = `/restaurants/${encodeURIComponent(queue.slug)}/`;
      actions.append(view);
      if (queue.status === "waiting") {
        const leave = make("button", "", "Leave the queue");
        leave.type = "button";
        leave.addEventListener("click", () => leaveQueue(queue));
        actions.append(leave);
      }
      card.append(info, number, actions);
      return card;
    }));
  }

  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }

  async function load(url, options) {
    const response = await fetch(url, { credentials: "same-origin", headers: { "X-CSRFToken": root.dataset.csrf }, ...options });
    let data = {};
    try { data = await response.json(); } catch (error) { /* e.g. a redirect to sign-in */ }
    if (Array.isArray(data.queues)) render(data.queues);
    showError(response.ok ? "" : data.error || "Something went wrong. Please reload the page.");
  }

  async function leaveQueue(queue) {
    if (!window.confirm(`Leave the queue at ${queue.restaurant}? You will lose ${queue.code}.`)) return;
    try {
      await load(root.dataset.urlLeave.replace(/0\/leave\/$/, `${queue.id}/leave/`), { method: "POST" });
    } catch (error) { showError("Could not reach the server. Try again."); }
  }

  async function refresh() {
    if (document.hidden) return;
    try { await load(root.dataset.urlData); } catch (error) { /* keep the last cards */ }
  }

  refresh();
  setInterval(refresh, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();
