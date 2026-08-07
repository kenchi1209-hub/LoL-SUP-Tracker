(function (global) {
  "use strict";

  function metricElement(name) {
    return global.document.querySelector(`[data-overview="${name}"]`);
  }

  function renderOverview(matches) {
    const metrics = global.RoleMetrics.aggregateMatches(matches);
    metricElement("games").textContent = `${metrics.games}戦`;
    metricElement("record").textContent = `${metrics.wins}勝 ${metrics.losses}敗`;

    const winrate = metricElement("winrate");
    winrate.classList.remove("good", "bad");
    if (!metrics.games) {
      winrate.textContent = "-";
      metricElement("avg-kda").textContent = "-";
      metricElement("kda").textContent = "-";
      metricElement("cspm").textContent = "-";
      metricElement("vspm").textContent = "-";
      metricElement("duration").textContent = "-";
      return metrics;
    }

    winrate.textContent = `${global.RoleMetrics.formatDecimal(metrics.winrate, 1)}%`;
    winrate.classList.add(metrics.winrate >= 50 ? "good" : "bad");
    metricElement("avg-kda").textContent = [
      global.RoleMetrics.formatDecimal(metrics.avgKills, 1),
      global.RoleMetrics.formatDecimal(metrics.avgDeaths, 1),
      global.RoleMetrics.formatDecimal(metrics.avgAssists, 1),
    ].join(" / ");
    metricElement("kda").textContent = global.RoleMetrics.formatDecimal(metrics.kda, 2);
    metricElement("cspm").textContent = global.RoleMetrics.formatDecimal(metrics.cspm, 2);
    metricElement("vspm").textContent = global.RoleMetrics.formatDecimal(metrics.vspm, 2);
    metricElement("duration").textContent = global.RoleMetrics.formatDuration(
      metrics.avgDurationSeconds
    );
    return metrics;
  }

  if (global.document) {
    global.document.addEventListener("role-filter:change", (event) => {
      renderOverview(event.detail.matches);
    });
  }

  const api = { render: renderOverview };
  global.RoleOverview = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
