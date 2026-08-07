(function (global) {
  "use strict";

  function formatDate(value) {
    return value ? value.replace(/-/g, "/") : "-";
  }

  function metricCell(value, digits, suffix) {
    const cell = global.document.createElement("td");
    cell.textContent = value === null || value === undefined
      ? "-"
      : `${global.RoleMetrics.formatDecimal(value, digits)}${suffix || ""}`;
    return cell;
  }

  function championIcons(champions, version) {
    const cell = global.document.createElement("td");
    const container = global.document.createElement("div");
    container.className = "patch-champions";
    champions.forEach((champion) => {
      const item = global.document.createElement("span");
      item.className = "patch-champion";
      const description = `${champion.name}、${champion.games}戦、勝率 ${global.RoleMetrics.formatDecimal(champion.winrate, 1)}%`;
      item.title = description;
      item.tabIndex = 0;
      item.setAttribute("role", "img");
      item.setAttribute("aria-label", description);
      const image = global.document.createElement("img");
      image.src = global.SiteUtils.championImageUrl(version, champion.iconId);
      image.alt = "";
      image.setAttribute("aria-hidden", "true");
      image.loading = "lazy";
      const count = global.document.createElement("span");
      count.className = "patch-champion-count";
      count.textContent = String(champion.games);
      count.setAttribute("aria-hidden", "true");
      item.append(image, count);
      container.append(item);
    });
    cell.append(container);
    return cell;
  }

  function renderPatchAnalysis(matches) {
    const section = global.document.querySelector(".patch-analysis");
    if (!section) return [];
    const rows = global.RolePatchMetrics.groupMatches(matches);
    const body = global.document.getElementById("patch-analysis-body");
    const empty = global.document.getElementById("patch-analysis-empty");
    empty.hidden = rows.length > 0;
    body.hidden = rows.length === 0;
    body.replaceChildren(...rows.map((row) => {
      const tableRow = global.document.createElement("tr");
      tableRow.dataset.patch = row.patch;
      if (row.reference) tableRow.className = "patch-reference";
      const patch = global.document.createElement("td");
      patch.className = "patch-label";
      patch.textContent = `${row.patch}（${formatDate(row.startDate)}～${formatDate(row.endDate)}）`;
      tableRow.append(
        patch,
        metricCell(row.metrics.games, 0),
        metricCell(row.metrics.winrate, 1, "%"),
        metricCell(row.metrics.kda, 2),
        metricCell(row.metrics.cspm, 2),
        metricCell(row.metrics.vspm, 2),
        metricCell(row.metrics.damagePerMinute, 0),
        championIcons(row.champions, section.dataset.ddragonVersion)
      );
      return tableRow;
    }));
    return rows;
  }

  if (global.document) {
    global.document.addEventListener("role-filter:change", (event) =>
      renderPatchAnalysis(event.detail.matches)
    );
  }

  const api = { render: renderPatchAnalysis, formatDate };
  global.RolePatchAnalysis = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
