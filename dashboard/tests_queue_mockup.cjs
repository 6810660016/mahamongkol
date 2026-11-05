// Run with: node dashboard/tests_queue_mockup.cjs
// Exercises user-visible queue transitions without a browser or external packages.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

class Element {
  constructor() { this.textContent = ""; this.children = []; this.events = {}; this.hidden = false; this.disabled = false; this.classList = { add() {}, remove() {} }; }
  addEventListener(type, callback) { this.events[type] = callback; }
  append(...elements) { this.children.push(...elements); }
  replaceChildren(...elements) { this.children = elements; }
  setAttribute() {}
  click() { if (!this.disabled) this.events.click?.({ target: this }); }
  close() { this.events.close?.(); }
  reset() {}
  reportValidity() { return true; }
}
const elements = new Map();
const get = (selector) => {
  if (!elements.has(selector)) elements.set(selector, new Element());
  return elements.get(selector);
};
const addButtons = [new Element(), new Element()];
const document = {
  querySelector: get,
  querySelectorAll(selector) { return selector === "[data-open-add]" ? addButtons : [new Element()]; },
  createElement() { return new Element(); },
};
const mockData = { source: "Walk-in", name: "Test guest", party: "3" };
const context = {
  document, Date, String, Number, Math,
  FormData: class { get(key) { return mockData[key]; } },
  clearTimeout() {}, setTimeout() {}, setInterval() {},
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "static/dashboard/js/owner_queue.js"), "utf8"), context);

const text = (selector) => get(selector).textContent;
const skippedRows = () => get("[data-skipped-list]").children;
assert.equal(text("[data-current-number]"), "Q008");
assert.equal(text("[data-stat-waiting]"), 5);
get("[data-skip]").click();
assert.equal(text("[data-current-number]"), "Q009", "skipping calls the next queue");
assert.equal(text("[data-stat-skipped]"), 2);
skippedRows()[1].children[1].click();
assert.equal(text("[data-current-number]"), "Q009", "recalling does not interrupt the current queue");
assert.equal(get("[data-waiting-list]").children[0].children[0].textContent, "Q008", "recalled queue is next");
get("[data-complete]").click();
assert.equal(text("[data-current-number]"), "Q008", "completion calls the recalled queue");
assert.equal(text("[data-stat-completed]"), 1);
get("[data-add-form]").events.submit({ preventDefault() {} });
assert.equal(get("[data-waiting-list]").children.at(-1).children[1].textContent, "Walk-in");
mockData.source = "Booking";
get("[data-add-form]").events.submit({ preventDefault() {} });
assert.equal(get("[data-waiting-list]").children.at(-1).children[1].textContent, "Booking");
get("[data-toggle-pause]").click();
assert.equal(addButtons[0].disabled, true, "pausing prevents adding sample queues");
const before = text("[data-stat-waiting]");
get("[data-add-form]").events.submit({ preventDefault() {} });
assert.equal(text("[data-stat-waiting]"), before);
get("[data-toggle-pause]").click();
assert.equal(addButtons[0].disabled, false);
console.log("Queue mockup transitions passed.");
