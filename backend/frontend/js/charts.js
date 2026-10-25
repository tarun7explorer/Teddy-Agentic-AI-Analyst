"use strict";

(() => {
  const palette = ["#7167d9", "#65a88a", "#e39b72", "#5c91c8", "#d7b451", "#9a78c7"];
  const instances = [];

  function textElement(parent, tag, text, className) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text == null ? "" : String(text);
    parent.append(element);
    return element;
  }

  function numberLabel(value, unit) {
    const formatted = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
    return unit ? `${formatted} ${unit}` : formatted;
  }

  function renderKpis(container, metrics) {
    container.replaceChildren();
    for (const metric of (metrics || []).slice(0, 12)) {
      if (!Number.isFinite(Number(metric.value))) continue;
      const card = document.createElement("article");
      card.className = "analytics-kpi";
      textElement(card, "span", metric.statistic || "calculated", "kpi-statistic");
      textElement(card, "strong", numberLabel(Number(metric.value), metric.unit), "kpi-value");
      textElement(card, "span", metric.label, "kpi-label");
      textElement(card, "span", `${metric.source_column || "Source data"} · ${referenceLabel(metric.source_reference)}`, "kpi-source");
      container.append(card);
    }
  }

  function buildDataTable(rows, parent) {
    const details = document.createElement("details");
    details.className = "chart-data-details";
    textElement(details, "summary", "Inspect calculated data");
    const data = (rows || []).slice(0, 100);
    const columns = [...new Set(data.flatMap((row) => Object.keys(row || {})))];
    if (!columns.length) {
      textElement(details, "p", "No underlying rows were returned.", "table-caption");
      parent.append(details);
      return;
    }
    const scroll = document.createElement("div");
    scroll.className = "table-scroll chart-data-scroll";
    const table = document.createElement("table");
    const head = document.createElement("thead");
    const headerRow = document.createElement("tr");
    for (const column of columns) textElement(headerRow, "th", column);
    head.append(headerRow);
    table.append(head);
    const body = document.createElement("tbody");
    for (const row of data) {
      const tr = document.createElement("tr");
      for (const column of columns) textElement(tr, "td", row[column] == null ? "" : row[column]);
      body.append(tr);
    }
    table.append(body);
    scroll.append(table);
    details.append(scroll);
    textElement(details, "p", `Source: ${referenceLabel(parent.dataset.sourceReference)}`, "table-caption");
    parent.append(details);
  }

  function referenceLabel(reference) {
    if (reference?.type === "page") return `page ${reference.page}`;
    if (reference?.type === "sheet") return `sheet ${reference.sheet}`;
    if (reference?.type === "csv") return `CSV rows ${reference.row_start}–${reference.row_end}`;
    if (reference?.type === "table") return `table ${reference.table}`;
    return reference?.type || "document table";
  }

  function renderChart(container, spec) {
    const labels = Array.isArray(spec?.labels) ? spec.labels.slice(0, 100) : [];
    const series = Array.isArray(spec?.series) ? spec.series.slice(0, 6) : [];
    const usable = labels.length >= 2 && series.some((item) =>
      Array.isArray(item.data) && item.data.length === labels.length
      && item.data.every((value) => Number.isFinite(Number(value)))
    );
    if (!usable) {
      const note = document.createElement("article");
      note.className = "chart-card chart-empty-data";
      textElement(note, "h4", spec?.title || "Chart unavailable", "chart-title");
      textElement(note, "p", "No complete numeric series was returned for this chart.", "chart-library-warning");
      container.append(note);
      return;
    }
    const card = document.createElement("article");
    card.className = "chart-card";
    card.dataset.sourceReference = JSON.stringify(spec.source_reference || {});
    textElement(card, "h4", spec.title, "chart-title");
    textElement(card, "p", `${spec.aggregation} · Source: ${referenceLabel(spec.source_reference)}`, "chart-subtitle");

    const canvasWrap = document.createElement("div");
    canvasWrap.className = "chart-canvas-wrap";
    const canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `${spec.chart_type} chart: ${spec.title}`);
    canvasWrap.append(canvas);
    card.append(canvasWrap);

    if (window.Chart) {
      const isDoughnut = spec.chart_type === "doughnut";
      const chartType = spec.chart_type === "line" ? "line" : isDoughnut ? "doughnut" : "bar";
      const total = series[0].data.reduce((sum, value) => sum + Number(value || 0), 0);
      const datasets = series.map((chartSeries, index) => ({
        label: chartSeries.name,
        data: chartSeries.data.slice(0, labels.length).map((value) => Number(value)),
        backgroundColor: isDoughnut
          ? spec.labels.map((_, colorIndex) => palette[colorIndex % palette.length])
          : palette[index % palette.length] + (chartType === "line" ? "" : "cc"),
        borderColor: palette[index % palette.length],
        borderWidth: chartType === "line" ? 2 : 1,
        pointRadius: chartType === "line" ? 3 : undefined,
        fill: false,
        tension: chartType === "line" ? 0.28 : 0,
      }));
      const instance = new window.Chart(canvas.getContext("2d"), {
        type: chartType,
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 180 },
          plugins: {
            legend: { display: isDoughnut || datasets.length > 1, position: "bottom", labels: { boxWidth: 9, usePointStyle: true, font: { size: 9 } } },
            tooltip: {
              callbacks: {
                label(context) {
                  const raw = Number(context.raw || 0);
                  if (isDoughnut) {
                    const share = total > 0 ? ` (${((raw / total) * 100).toFixed(1)}%)` : "";
                    return `${context.label}: ${numberLabel(raw, spec.unit)}${share}`;
                  }
                  return `${context.dataset.label}: ${numberLabel(raw, spec.unit)}`;
                },
              },
            },
          },
          scales: isDoughnut ? {} : {
            x: { title: { display: true, text: spec.x_axis_label }, grid: { display: false }, ticks: { maxRotation: 35, minRotation: 0 } },
            y: { beginAtZero: spec.chart_type !== "line", title: { display: true, text: spec.y_axis_label }, ticks: { precision: 2 } },
          },
        },
      });
      instances.push(instance);
    } else {
      textElement(card, "p", "The chart library could not be loaded. The calculated values remain available below.", "chart-library-warning");
    }

    buildDataTable(spec.underlying_data, card);
    container.append(card);
  }

  function renderTable(parent, title, columns, rows, sourceReference) {
    const details = document.createElement("details");
    details.className = "comparison-table-details";
    textElement(details, "summary", `${title} · inspect rows`);
    const scroll = document.createElement("div");
    scroll.className = "table-scroll";
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    for (const column of columns) textElement(headerRow, "th", column);
    thead.append(headerRow);
    table.append(thead);
    const tbody = document.createElement("tbody");
    for (const row of rows.slice(0, 100)) {
      const tr = document.createElement("tr");
      for (const column of columns) textElement(tr, "td", row[column] ?? "");
      tbody.append(tr);
    }
    table.append(tbody);
    scroll.append(table);
    details.append(scroll);
    textElement(details, "p", `Source: ${referenceLabel(sourceReference)}`, "table-caption");
    parent.append(details);
  }

  function renderTimelines(container, events) {
    container.replaceChildren();
    for (const item of (events || []).slice(0, 100)) {
      const row = document.createElement("li");
      textElement(row, "time", item.date);
      textElement(row, "span", item.event);
      textElement(row, "small", referenceLabel(item.source_reference));
      container.append(row);
    }
  }

  function clear() {
    while (instances.length) instances.pop().destroy();
    const kpis = document.querySelector("#analytics-kpis");
    const chartsGrid = document.querySelector("#charts-grid");
    const content = document.querySelector("#analytics-content");
    const chartEmpty = document.querySelector("#chart-empty-state");
    const comparisons = document.querySelector("#comparison-tables");
    const comparisonBlock = document.querySelector("#analytics-comparisons");
    const timeline = document.querySelector("#timeline-events");
    const timelineBlock = document.querySelector("#analytics-timeline");
    const warnings = document.querySelector("#analytics-warnings");
    kpis.replaceChildren();
    chartsGrid.replaceChildren();
    comparisons.replaceChildren();
    comparisonBlock.hidden = true;
    timeline.replaceChildren();
    timelineBlock.hidden = true;
    warnings.replaceChildren();
    warnings.hidden = true;
    content.hidden = true;
    chartEmpty.hidden = false;
    chartEmpty.querySelector("p").textContent = "Charts appear when Teddy finds enough structured data to support them.";
  }

  function render(analytics) {
    clear();
    const kpis = document.querySelector("#analytics-kpis");
    const chartsGrid = document.querySelector("#charts-grid");
    const chartEmpty = document.querySelector("#chart-empty-state");
    const content = document.querySelector("#analytics-content");
    const comparisonBlock = document.querySelector("#analytics-comparisons");
    const comparisonTables = document.querySelector("#comparison-tables");
    const timelineBlock = document.querySelector("#analytics-timeline");
    const timeline = document.querySelector("#timeline-events");
    const warnings = document.querySelector("#analytics-warnings");
    kpis.replaceChildren();
    chartsGrid.replaceChildren();
    comparisonTables.replaceChildren();
    timeline.replaceChildren();
    warnings.replaceChildren();

    renderKpis(kpis, analytics?.metrics);
    const charts = (analytics?.charts || []).slice(0, 8);
    for (const spec of charts) renderChart(chartsGrid, spec);
    const renderedCharts = chartsGrid.childElementCount;
    chartEmpty.hidden = renderedCharts > 0;
    const message = chartEmpty.querySelector("p");
    message.textContent = analytics?.warnings?.find((warning) => warning.includes("No chart-ready"))
      || (renderedCharts ? "" : "No chart is supported by this document’s extracted data.");

    const comparisons = (analytics?.comparison_tables || []).slice(0, 8);
    comparisonBlock.hidden = comparisons.length === 0;
    for (const item of comparisons) {
      const columns = item.rows?.length ? Object.keys(item.rows[0]) : [];
      renderTable(comparisonTables, item.title, columns, item.rows || [], item.source_reference);
    }
    const events = (analytics?.timelines || []).slice(0, 100);
    timelineBlock.hidden = events.length === 0;
    renderTimelines(timeline, events);

    if (analytics?.warnings?.length) {
      warnings.hidden = false;
      for (const warning of analytics.warnings) textElement(warnings, "p", warning);
    } else {
      warnings.hidden = true;
    }
    const hasContent = Boolean((analytics?.metrics || []).length || charts.length || comparisons.length || events.length || (analytics?.profiles || []).length);
    content.hidden = !hasContent;
    chartEmpty.hidden = renderedCharts > 0;
    chartEmpty.dataset.hasAnalytics = hasContent ? "true" : "false";
    if (!renderedCharts && hasContent) chartEmpty.hidden = false;
  }

  window.TeddyCharts = { render, clear };
})();
