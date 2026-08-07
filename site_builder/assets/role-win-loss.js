(function (global) {
  "use strict";

  function formatValue(value, definition) {
    if (value === null || value === undefined) return "-";
    if (definition.format === "duration") {
      return global.RoleMetrics.formatDuration(value);
    }
    return `${global.RoleMetrics.formatDecimal(value, definition.digits)}` +
      (definition.suffix || "");
  }

  function formatDifference(value, definition) {
    if (value === null || value === undefined) return "-";
    const sign = value >= 0 ? "+" : "-";
    if (definition.format === "duration") {
      return `${sign}${global.RoleMetrics.formatDuration(Math.abs(value))}`;
    }
    return `${sign}${global.RoleMetrics.formatDecimal(Math.abs(value), definition.digits)}` +
      (definition.suffix || "");
  }

  function cell(text, className) {
    const element = global.document.createElement("td");
    element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  function renderWinLoss(matches) {
    const section = global.document.querySelector("[data-win-loss-role]");
    if (!section) return null;
    const comparison = global.RoleWinLossMetrics.compareMatches(
      matches,
      section.dataset.winLossRole
    );
    global.document.getElementById("win-loss-counts").textContent =
      `勝利時 ${comparison.winGames}戦 / 敗北時 ${comparison.lossGames}戦`;
    const body = global.document.getElementById("win-loss-body");
    body.replaceChildren(
      ...comparison.rows.map((row) => {
        const tableRow = global.document.createElement("tr");
        tableRow.dataset.comparisonMetric = row.definition.key;
        tableRow.append(
          cell(row.definition.label),
          cell(formatValue(row.winValue, row.definition)),
          cell(formatValue(row.lossValue, row.definition)),
          cell(formatDifference(row.difference, row.definition), row.tone)
        );
        return tableRow;
      })
    );
    return comparison;
  }

  if (global.document) {
    global.document.addEventListener("role-filter:change", (event) => {
      renderWinLoss(event.detail.matches);
    });
  }

  const api = { render: renderWinLoss, formatDifference, formatValue };
  global.RoleWinLoss = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
