const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const frontend = path.resolve(__dirname, "..");
let passed = 0;

function test(name, run) {
  run();
  passed += 1;
  process.stdout.write(`PASS ${name}\n`);
}

class FakeElement {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.attributes = {};
    this.hidden = false;
    this.textContent = "";
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = [...items]; }
  setAttribute(key, value) { this.attributes[key] = value; }
  querySelector() {
    if (!this.paragraph) this.paragraph = new FakeElement("p");
    return this.paragraph;
  }
  get childElementCount() { return this.children.length; }
}

function loadCharts() {
  const selectors = [
    "#analytics-kpis", "#charts-grid", "#analytics-content", "#chart-empty-state",
    "#comparison-tables", "#analytics-comparisons", "#timeline-events",
    "#analytics-timeline", "#analytics-warnings",
  ];
  const nodes = Object.fromEntries(selectors.map((selector) => [selector, new FakeElement()]));
  nodes["#chart-empty-state"].paragraph = new FakeElement("p");
  const document = {
    createElement: (tag) => new FakeElement(tag),
    querySelector: (selector) => nodes[selector],
  };
  const window = {};
  const source = fs.readFileSync(path.join(frontend, "js", "charts.js"), "utf8");
  vm.runInNewContext(source, { window, document, Intl, Number, Set, JSON });
  return { charts: window.TeddyCharts, nodes };
}

test("dashboard chart renderer handles a genuinely empty analytics result", () => {
  const { charts, nodes } = loadCharts();
  charts.render({ status: "no_suitable_data", charts: [], metrics: [], comparison_tables: [], timelines: [], profiles: [] });
  assert.equal(nodes["#analytics-content"].hidden, true);
  assert.equal(nodes["#chart-empty-state"].hidden, false);
  assert.match(nodes["#chart-empty-state"].paragraph.textContent, /No chart/);
});

test("malformed empty chart series render a safe explanation instead of crashing", () => {
  const { charts, nodes } = loadCharts();
  charts.render({
    status: "available", charts: [{ chart_type: "bar", title: "Empty", labels: [], series: [], underlying_data: [] }],
    metrics: [], comparison_tables: [], timelines: [], profiles: [],
  });
  const card = nodes["#charts-grid"].children[0];
  assert.ok(card);
  assert.match(card.children[1].textContent, /No complete numeric series/);
});

test("dashboard inserts document and model text through safe DOM APIs", () => {
  const app = fs.readFileSync(path.join(frontend, "js", "app.js"), "utf8");
  assert.doesNotMatch(app, /\.innerHTML\b/);
  assert.match(app, /extractedText\.textContent = text\.slice/);
  assert.match(app, /bubble\.textContent = text/);
  assert.match(app, /element\.textContent = text/);
  assert.match(app, /item\.quote, "highlight-quote"/);
});

test("workflow states, warnings, evidence, and verification have accessible UI targets", () => {
  const html = fs.readFileSync(path.join(frontend, "index.html"), "utf8");
  for (const id of ["workflow-overview", "workflow-status", "workflow-provider", "workflow-verification", "workflow-warnings", "document-highlights"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /aria-live="polite"/);
});

process.stdout.write(`${passed} dashboard smoke checks passed.\n`);
